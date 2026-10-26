"""HTTP API and static dashboard."""

from __future__ import annotations

import html
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..analytics import kpis
from ..pricing import inr
from ..service import RenewFlow
from ..store import CHANNELS
from . import views

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ReplyIn(BaseModel):
    customer_id: int
    channel: str
    text: str = Field(min_length=1, max_length=2000)


class ReadIn(BaseModel):
    message_id: int


class PayIn(BaseModel):
    token: str


class CohortIn(BaseModel):
    count: int = Field(20, ge=1, le=40)


class ResolveIn(BaseModel):
    note: str = Field("", max_length=500)


class SettingsIn(BaseModel):
    quiet_hours: Literal["on", "off"] | None = None


def create_app(svc: RenewFlow | None = None) -> FastAPI:
    svc = svc or RenewFlow.create()
    svc.seed_if_empty()
    app = FastAPI(title="RenewFlow", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    store = svc.store
    if svc.settings.webhook_token:
        from .webhooks import build_router

        app.include_router(build_router(svc, svc.settings))

    def guard(fn):
        try:
            return fn()
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------------ read
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/version")
    def version():
        return {"version": store.version}

    @app.get("/api/meta")
    def meta():
        return {
            "mode": svc.settings.mode,
            "model": svc.model.name,
            "channels": list(svc.settings.enabled_channels),
            "simulated_channels": [
                c for c in svc.settings.enabled_channels
                if svc.settings.mode == "local" or c in svc.settings.local_channels
            ],
            "all_channels": list(CHANNELS),
            "quiet_hours": store.get_setting("quiet_hours", "on"),
            "synthetic_data": True,
        }

    @app.get("/api/overview")
    def overview():
        return kpis.overview(store, svc.settings)

    @app.get("/api/customers")
    def customers():
        return views.customer_rows(svc)

    @app.get("/api/customers/{customer_id}")
    def customer(customer_id: int):
        detail = views.customer_detail(svc, customer_id)
        if detail is None:
            raise HTTPException(404, "customer_not_found")
        return detail

    @app.get("/api/handoffs")
    def handoffs():
        return store.list_handoffs()

    # ------------------------------------------------------------------ agent actions
    @app.post("/api/renewals/{policy_id}/start")
    def start(policy_id: int):
        return asdict(guard(lambda: svc.start_renewal(policy_id)))

    @app.post("/api/simulator/reply")
    def reply(body: ReplyIn):
        return asdict(guard(lambda: svc.inbound(body.customer_id, body.channel, body.text)))

    @app.post("/api/simulator/read")
    def read(body: ReadIn):
        return {"recorded": svc.open_message(body.message_id)}

    @app.post("/api/simulator/pay")
    def pay(body: PayIn):
        return guard(lambda: svc.pay(body.token))

    @app.post("/api/simulator/cohort")
    def cohort(body: CohortIn):
        return svc.run_cohort(body.count)

    @app.post("/api/handoffs/{handoff_id}/resolve")
    def resolve(handoff_id: int, body: ResolveIn):
        guard(lambda: svc.resolve_handoff(handoff_id, body.note))
        return {"ok": True}

    @app.post("/api/settings")
    def update_settings(body: SettingsIn):
        if body.quiet_hours:
            store.set_setting("quiet_hours", body.quiet_hours)
        return meta()

    @app.post("/api/reset")
    def reset():
        svc.reset()
        return {"ok": True}

    # ------------------------------------------------------------------ payment page
    def _page(title: str, body: str) -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>{html.escape(title)}</title><style>"
            "body{font:16px/1.5 system-ui,sans-serif;margin:0;display:grid;place-items:center;"
            "min-height:100vh;background:#f4f6f8;color:#14202b}main{background:#fff;max-width:420px;"
            "width:calc(100% - 32px);padding:28px;border-radius:16px;box-shadow:0 1px 3px #0002}"
            "h1{font-size:20px;margin:0 0 4px}p{margin:6px 0;color:#4a5a68}b{color:#14202b}"
            "button{margin-top:18px;width:100%;font:inherit;font-weight:600;padding:12px;border:0;"
            "border-radius:10px;background:#0b6bcb;color:#fff;cursor:pointer}"
            "small{display:block;margin-top:14px;color:#6b7a88}</style><main>"
            f"{body}</main>"
        )

    @app.get("/pay/{token}", response_class=HTMLResponse)
    def pay_page(token: str):
        quote = store.quote_by_token(token)
        if quote is None:
            return _page("Link not found", "<h1>Link not found</h1><p>This payment link is not valid.</p>")
        svc.click(token)
        policy = store.get_policy(quote.policy_id)
        amount = (
            inr(quote.total) if quote.installments == 1
            else f"{quote.installments} × {inr(quote.per_installment)}"
        )
        if policy.status == "renewed":
            return _page("Already renewed", "<h1>Already renewed</h1><p>Nothing more to do.</p>")
        return _page(
            "Renew your policy",
            f"<h1>Renew your policy</h1><p>{html.escape(policy.product)}<br>"
            f"{html.escape(policy.asset)}</p><p><b>{html.escape(quote.plan.capitalize())} plan: "
            f"{html.escape(amount)}</b></p><form method=post><button>Pay now (demo)</button></form>"
            "<small>Demonstration only. No real payment is taken.</small>",
        )

    @app.post("/pay/{token}", response_class=HTMLResponse)
    def pay_confirm(token: str):
        try:
            svc.pay(token)
        except LookupError:
            return _page("Link not found", "<h1>Link not found</h1>")
        return _page("Renewed", "<h1>Payment received</h1><p>Your policy is renewed. Thank you!</p>")

    # Static dashboard last, so it never shadows the routes above.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
    return app
