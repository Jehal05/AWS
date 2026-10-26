"""The application facade: wiring plus the few operations that are not the agent's job."""

from __future__ import annotations

from typing import Any

from .agent.guardrails import Guardrails
from .agent.orchestrator import RenewalAgent, RunResult
from .channels.base import Channel
from .channels.registry import build_channels
from .clock import Clock
from .config import Settings
from .db import Database
from .llm import build_model
from .llm.base import ChatModel
from .pricing import inr
from .seed import seed_demo
from .simulation import run_cohort
from .store import Store

PLAN_NAME = {"annual": "annual", "quarterly": "quarterly", "monthly": "monthly"}


class RenewFlow:
    def __init__(
        self, settings: Settings, store: Store, channels: dict[str, Channel], model: ChatModel
    ):
        self.settings = settings
        self.store = store
        self.channels = channels
        self.model = model
        self.guardrails = Guardrails(store, settings)
        self.agent = RenewalAgent(store, channels, model, settings, self.guardrails)

    @classmethod
    def create(cls, settings: Settings | None = None, clock: Clock | None = None) -> RenewFlow:
        settings = settings or Settings()
        store = Store(Database(settings.db_path), clock)
        return cls(settings, store, build_channels(settings), build_model(settings))

    # ------------------------------------------------------------------ lifecycle
    def seed_if_empty(self) -> bool:
        if self.store.db.scalar("SELECT COUNT(*) FROM customers"):
            return False
        seed_demo(self.store)
        return True

    def reset(self) -> None:
        with self.agent.global_lock:
            self.store.db.reset()
            seed_demo(self.store)
            self.store._bump()

    # ------------------------------------------------------------------ agent operations
    def start_renewal(self, policy_id: int) -> RunResult:
        return self.agent.start_renewal(policy_id)

    def inbound(self, customer_id: int, channel: str, text: str) -> RunResult:
        return self.agent.handle_inbound(customer_id, channel, text)

    def run_cohort(self, count: int, rng_seed: int | None = None) -> dict[str, Any]:
        return run_cohort(self, count, rng_seed)

    # ------------------------------------------------------------------ customer actions
    def open_message(self, message_id: int) -> bool:
        """The customer opened a message on their device."""
        return self.store.mark_read(message_id)

    def click(self, token: str) -> bool:
        """The customer followed a payment link. Recorded once per message."""
        quote = self.store.quote_by_token(token)
        if quote is None:
            raise LookupError("unknown_payment_link")
        if not quote.message_id or self.store.has_event(quote.message_id, "clicked"):
            return False
        message = self.store.get_message(quote.message_id)
        self.store.mark_read(quote.message_id)
        self.store.log_event(
            message["customer_id"], message["channel"], "clicked", message["thread_id"],
            quote.message_id,
        )
        return True

    def pay(self, token: str) -> dict[str, Any]:
        """Complete a (simulated) payment: renew the policy and confirm to the customer."""
        with self.agent.global_lock:
            store = self.store
            quote = store.quote_by_token(token)
            if quote is None:
                raise LookupError("unknown_payment_link")
            policy = store.get_policy(quote.policy_id)
            if policy.status == "renewed":
                return {"ok": True, "already_renewed": True, "policy_id": policy.id}
            self.click(token)
            store.mark_renewed(policy.id, quote.plan, quote.total)
            thread_id = quote.thread_id or store.open_thread(policy.customer_id, policy.id)
            store.set_thread_status(thread_id, "renewed")
            channel = self._reply_channel(thread_id)
            store.log_event(
                policy.customer_id, channel, "renewed", thread_id, quote.message_id,
                meta={"plan": quote.plan, "amount": quote.total},
            )
            customer = store.get_customer(policy.customer_id)
            if quote.installments == 1:
                plan_text = f"annual plan ({inr(quote.total)})"
            else:
                plan_text = f"{quote.plan} plan ({quote.installments} × {inr(quote.per_installment)})"
            confirmation = self.agent.send_system(
                customer.id, thread_id, channel,
                f"Payment received. Your {policy.product} is renewed on the {plan_text}. "
                f"Thank you, {customer.first_name}!",
                allowed_amounts=(quote.total, quote.per_installment),
            )
            return {"ok": True, "policy_id": policy.id, "plan": quote.plan, "amount": quote.total,
                    "confirmation_sent": bool(confirmation.get("ok"))}

    def _reply_channel(self, thread_id: int) -> str:
        messages = self.store.thread_messages(thread_id)
        for m in reversed(messages):
            if m["direction"] == "in":
                return m["channel"]
        for m in reversed(messages):
            if m["direction"] == "out":
                return m["channel"]
        return self.settings.enabled_channels[0]

    def resolve_handoff(self, handoff_id: int, note: str) -> None:
        self.store.resolve_handoff(handoff_id, note.strip()[:500])
