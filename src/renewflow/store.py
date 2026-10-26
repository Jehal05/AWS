"""Data access layer. Every write goes through here so the UI can poll one version counter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from .clock import Clock, iso
from .db import Database

CHANNELS = ("whatsapp", "email", "sms")


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    email: str | None
    phone: str | None
    language: str
    timezone: str
    persona: str

    @property
    def first_name(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class Policy:
    id: int
    customer_id: int
    policy_number: str
    product: str
    asset: str
    expiry_date: str
    premium_prev: int
    premium_new: int
    sum_insured: int
    ncb_percent: int
    increase_reasons: list[dict[str, Any]]
    status: str
    renewed_at: str | None
    renewed_plan: str | None
    renewed_amount: int | None

    @property
    def delta(self) -> int:
        return self.premium_new - self.premium_prev

    def days_to_expiry(self, today: date) -> int:
        return (date.fromisoformat(self.expiry_date) - today).days


@dataclass(frozen=True)
class QuoteRow:
    id: int
    policy_id: int
    thread_id: int | None
    plan: str
    installments: int
    per_installment: int
    total: int
    surcharge: int
    token: str
    message_id: int | None
    created_at: str


def _policy(row: dict[str, Any]) -> Policy:
    return Policy(**{**row, "increase_reasons": json.loads(row["increase_reasons"])})


class Store:
    def __init__(self, db: Database, clock: Clock | None = None):
        self.db = db
        self.clock = clock or Clock()
        self._version = 0

    # ------------------------------------------------------------------ plumbing
    @property
    def version(self) -> int:
        return self._version

    def _bump(self) -> None:
        self._version += 1

    def now_iso(self) -> str:
        return iso(self.clock.now())

    # ------------------------------------------------------------------ customers
    def add_customer(
        self,
        name: str,
        email: str | None,
        phone: str | None,
        persona: str = "balanced",
        language: str = "en",
        timezone: str = "Asia/Kolkata",
    ) -> int:
        cid = self.db.execute(
            "INSERT INTO customers (name, email, phone, language, timezone, persona)"
            " VALUES (?,?,?,?,?,?)",
            (name, email, phone, language, timezone, persona),
        )
        self._bump()
        return cid

    def get_customer(self, customer_id: int) -> Customer | None:
        row = self.db.one("SELECT * FROM customers WHERE id=?", (customer_id,))
        return Customer(**row) if row else None

    def all_customers(self) -> list[Customer]:
        return [Customer(**r) for r in self.db.query("SELECT * FROM customers ORDER BY id")]

    # ------------------------------------------------------------------ consent
    def set_consent(self, customer_id: int, channel: str, opted_in: bool) -> None:
        self.db.execute(
            "INSERT INTO consents (customer_id, channel, opted_in, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(customer_id, channel) DO UPDATE SET"
            " opted_in=excluded.opted_in, updated_at=excluded.updated_at",
            (customer_id, channel, int(opted_in), self.now_iso()),
        )
        self._bump()

    def consents(self, customer_id: int) -> dict[str, bool]:
        rows = self.db.query(
            "SELECT channel, opted_in FROM consents WHERE customer_id=?", (customer_id,)
        )
        found = {r["channel"]: bool(r["opted_in"]) for r in rows}
        return {c: found.get(c, False) for c in CHANNELS}

    def revoke_all_consents(self, customer_id: int) -> None:
        for channel in CHANNELS:
            self.set_consent(customer_id, channel, False)

    # ------------------------------------------------------------------ policies
    def add_policy(self, customer_id: int, **fields: Any) -> int:
        reasons = json.dumps(fields.pop("increase_reasons", []))
        columns = ["customer_id", "increase_reasons", *fields.keys()]
        values = [customer_id, reasons, *fields.values()]
        marks = ",".join("?" for _ in columns)
        pid = self.db.execute(
            f"INSERT INTO policies ({','.join(columns)}) VALUES ({marks})", values
        )
        self._bump()
        return pid

    def get_policy(self, policy_id: int) -> Policy | None:
        row = self.db.one("SELECT * FROM policies WHERE id=?", (policy_id,))
        return _policy(row) if row else None

    def renewal_policy_for(self, customer_id: int) -> Policy | None:
        row = self.db.one(
            "SELECT * FROM policies WHERE customer_id=? ORDER BY expiry_date, id LIMIT 1",
            (customer_id,),
        )
        return _policy(row) if row else None

    def all_policies(self) -> list[Policy]:
        return [_policy(r) for r in self.db.query("SELECT * FROM policies ORDER BY id")]

    def mark_renewed(self, policy_id: int, plan: str, amount: int) -> None:
        self.db.execute(
            "UPDATE policies SET status='renewed', renewed_at=?, renewed_plan=?, renewed_amount=?"
            " WHERE id=?",
            (self.now_iso(), plan, amount, policy_id),
        )
        self._bump()

    # ------------------------------------------------------------------ threads
    def open_thread(self, customer_id: int, policy_id: int | None = None) -> int:
        row = self.db.one(
            "SELECT id FROM threads WHERE customer_id=? AND status!='closed'"
            " ORDER BY id DESC LIMIT 1",
            (customer_id,),
        )
        if row:
            return row["id"]
        now = self.now_iso()
        tid = self.db.execute(
            "INSERT INTO threads (customer_id, policy_id, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?)",
            (customer_id, policy_id, "open", now, now),
        )
        self._bump()
        return tid

    def thread_for(self, customer_id: int) -> dict[str, Any] | None:
        return self.db.one(
            "SELECT * FROM threads WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
        )

    def get_thread(self, thread_id: int) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM threads WHERE id=?", (thread_id,))

    def set_thread_status(self, thread_id: int, status: str) -> None:
        self.db.execute(
            "UPDATE threads SET status=?, updated_at=? WHERE id=?",
            (status, self.now_iso(), thread_id),
        )
        self._bump()

    # ------------------------------------------------------------------ messages
    def add_message(
        self,
        thread_id: int,
        customer_id: int,
        channel: str,
        direction: str,
        sender: str,
        body: str,
        subject: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        mid = self.db.execute(
            "INSERT INTO messages (thread_id, customer_id, channel, direction, sender, subject,"
            " body, meta, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                thread_id,
                customer_id,
                channel,
                direction,
                sender,
                subject,
                body,
                json.dumps(meta or {}),
                self.now_iso(),
            ),
        )
        self.db.execute(
            "UPDATE threads SET updated_at=? WHERE id=?", (self.now_iso(), thread_id)
        )
        self._bump()
        return mid

    def _message(self, row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "meta": json.loads(row["meta"])}

    def thread_messages(self, thread_id: int) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM messages WHERE thread_id=? ORDER BY id", (thread_id,))
        return [self._message(r) for r in rows]

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM messages WHERE id=?", (message_id,))
        return self._message(row) if row else None

    def message_by_provider_id(self, provider_id: str, direction: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM messages WHERE json_extract(meta, '$.provider_id') = ?"
        args: tuple[Any, ...] = (provider_id,)
        if direction:
            sql += " AND direction = ?"
            args += (direction,)
        row = self.db.one(sql + " ORDER BY id LIMIT 1", args)
        return self._message(row) if row else None

    def customer_by_phone(self, phone: str) -> Customer | None:
        """Match on digits only, so '+91 98765 43210' and '919876543210' are the same number."""
        wanted = "".join(ch for ch in phone if ch.isdigit())
        for customer in self.all_customers():
            if customer.phone and "".join(c for c in customer.phone if c.isdigit()) == wanted:
                return customer
        return None

    def customer_by_email(self, email: str) -> Customer | None:
        wanted = email.strip().lower()
        return next((c for c in self.all_customers() if (c.email or "").lower() == wanted), None)

    # ------------------------------------------------------------------ events
    def log_event(
        self,
        customer_id: int,
        channel: str,
        type_: str,
        thread_id: int | None = None,
        message_id: int | None = None,
        meta: dict[str, Any] | None = None,
        ts: str | None = None,
    ) -> int:
        eid = self.db.execute(
            "INSERT INTO events (customer_id, thread_id, message_id, channel, type, meta, ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (customer_id, thread_id, message_id, channel, type_, json.dumps(meta or {}),
             ts or self.now_iso()),
        )
        self._bump()
        return eid

    def has_event(self, message_id: int, type_: str) -> bool:
        return bool(
            self.db.scalar(
                "SELECT 1 FROM events WHERE message_id=? AND type=? LIMIT 1", (message_id, type_)
            )
        )

    def events_for(self, customer_id: int) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT * FROM events WHERE customer_id=? ORDER BY ts, id", (customer_id,)
        )

    def mark_read(self, message_id: int) -> bool:
        """Log a read event for an outbound message, once. Returns True if newly recorded."""
        message = self.get_message(message_id)
        if not message or message["direction"] != "out" or self.has_event(message_id, "read"):
            return False
        self.log_event(
            message["customer_id"], message["channel"], "read", message["thread_id"], message_id
        )
        return True

    def mark_read_on_reply(self, thread_id: int, channel: str) -> None:
        """A customer who replies has plainly read what they replied to."""
        for m in self.thread_messages(thread_id):
            if m["direction"] == "out" and m["channel"] == channel:
                self.mark_read(m["id"])

    # ------------------------------------------------------------------ quotes
    def add_quote(self, policy_id: int, thread_id: int | None, quote: Any, token: str) -> int:
        qid = self.db.execute(
            "INSERT INTO quotes (policy_id, thread_id, plan, installments, per_installment,"
            " total, surcharge, token, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (policy_id, thread_id, quote.plan, quote.installments, quote.per_installment,
             quote.total, quote.surcharge, token, self.now_iso()),
        )
        self._bump()
        return qid

    def latest_quote(self, policy_id: int) -> QuoteRow | None:
        row = self.db.one(
            "SELECT * FROM quotes WHERE policy_id=? ORDER BY id DESC LIMIT 1", (policy_id,)
        )
        return QuoteRow(**row) if row else None

    def quote_by_token(self, token: str) -> QuoteRow | None:
        row = self.db.one("SELECT * FROM quotes WHERE token=?", (token,))
        return QuoteRow(**row) if row else None

    def attach_quote_message(self, token: str, message_id: int) -> None:
        self.db.execute("UPDATE quotes SET message_id=? WHERE token=?", (message_id, token))

    def quotes_for_policy(self, policy_id: int) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM quotes WHERE policy_id=? ORDER BY id", (policy_id,))

    # ------------------------------------------------------------------ follow-ups
    def add_followup(
        self, thread_id: int, customer_id: int, channel: str, due_at: str, note: str
    ) -> int:
        fid = self.db.execute(
            "INSERT INTO followups (thread_id, customer_id, channel, due_at, note, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (thread_id, customer_id, channel, due_at, note, self.now_iso()),
        )
        self._bump()
        return fid

    def followups_for(self, customer_id: int) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT * FROM followups WHERE customer_id=? ORDER BY due_at", (customer_id,)
        )

    # ------------------------------------------------------------------ handoffs
    def add_handoff(self, thread_id: int, customer_id: int, reason: str, summary: str) -> int:
        hid = self.db.execute(
            "INSERT INTO handoffs (thread_id, customer_id, reason, summary, created_at)"
            " VALUES (?,?,?,?,?)",
            (thread_id, customer_id, reason, summary, self.now_iso()),
        )
        self.set_thread_status(thread_id, "handoff")
        self.log_event(customer_id, "-", "handoff", thread_id, meta={"reason": reason})
        return hid

    def get_handoff(self, handoff_id: int) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM handoffs WHERE id=?", (handoff_id,))

    def list_handoffs(self) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT h.*, c.name AS customer_name FROM handoffs h"
            " JOIN customers c ON c.id=h.customer_id"
            " ORDER BY (h.status='open') DESC, h.id DESC"
        )

    def resolve_handoff(self, handoff_id: int, note: str) -> None:
        handoff = self.get_handoff(handoff_id)
        if not handoff:
            raise LookupError("handoff_not_found")
        self.db.execute(
            "UPDATE handoffs SET status='resolved', resolved_at=?, resolution_note=? WHERE id=?",
            (self.now_iso(), note, handoff_id),
        )
        thread = self.get_thread(handoff["thread_id"])
        if thread and thread["status"] == "handoff":
            self.set_thread_status(thread["id"], "open")
        self._bump()

    # ------------------------------------------------------------------ agent runs
    def start_run(self, thread_id: int, customer_id: int, trigger: str) -> int:
        rid = self.db.execute(
            "INSERT INTO agent_runs (thread_id, customer_id, trigger, started_at) VALUES (?,?,?,?)",
            (thread_id, customer_id, trigger, self.now_iso()),
        )
        self._bump()
        return rid

    def finish_run(
        self, run_id: int, duration_ms: int, steps: int, outcome: str, summary: str | None
    ) -> None:
        self.db.execute(
            "UPDATE agent_runs SET duration_ms=?, steps=?, outcome=?, summary=? WHERE id=?",
            (duration_ms, steps, outcome, summary, run_id),
        )
        self._bump()

    def log_tool_call(
        self, run_id: int, thread_id: int, name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> None:
        self.db.execute(
            "INSERT INTO tool_calls (run_id, thread_id, name, args, result, ok, ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (run_id, thread_id, name, json.dumps(args, default=str),
             json.dumps(result, default=str), int(bool(result.get("ok", True))), self.now_iso()),
        )
        self._bump()

    def trace_for_thread(self, thread_id: int) -> list[dict[str, Any]]:
        runs = self.db.query("SELECT * FROM agent_runs WHERE thread_id=? ORDER BY id", (thread_id,))
        calls = self.db.query("SELECT * FROM tool_calls WHERE thread_id=? ORDER BY id", (thread_id,))
        by_run: dict[int, list[dict[str, Any]]] = {}
        for c in calls:
            by_run.setdefault(c["run_id"], []).append(
                {
                    "name": c["name"],
                    "args": json.loads(c["args"]),
                    "result": json.loads(c["result"]),
                    "ok": bool(c["ok"]),
                    "ts": c["ts"],
                }
            )
        return [{**r, "tool_calls": by_run.get(r["id"], [])} for r in runs]

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: str) -> str:
        row = self.db.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._bump()
