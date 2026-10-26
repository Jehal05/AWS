"""The agent loop: build context, let the model call tools, enforce limits, record everything."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..channels.base import Channel
from ..config import Settings
from ..llm.base import ChatModel
from ..store import CHANNELS, Store
from .guardrails import Guardrails, is_opt_in, is_opt_out
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SPECS, ToolContext, execute_tool

log = logging.getLogger("renewflow.agent")


@dataclass
class RunResult:
    run_id: int
    thread_id: int
    outcome: str
    summary: str | None = None
    messages_sent: int = 0
    handoff: bool = False
    paused: bool = False
    steps: int = 0
    blocked: list[dict[str, Any]] = field(default_factory=list)


class RenewalAgent:
    def __init__(
        self,
        store: Store,
        channels: dict[str, Channel],
        model: ChatModel,
        settings: Settings,
        guardrails: Guardrails,
    ):
        self.store = store
        self.channels = channels
        self.model = model
        self.settings = settings
        self.guardrails = guardrails
        # One lock for every agent action keeps the demo deterministic and the cohort
        # simulator from interleaving with live clicks.
        self.global_lock = threading.RLock()

    # ------------------------------------------------------------------ entry points
    def start_renewal(self, policy_id: int) -> RunResult:
        """Proactive: the renewal is coming up, reach out on the best channel."""
        with self.global_lock:
            policy = self.store.get_policy(policy_id)
            if policy is None:
                raise LookupError("policy_not_found")
            thread_id = self.store.open_thread(policy.customer_id, policy.id)
            thread = self.store.get_thread(thread_id)
            if policy.status != "open" or thread["status"] in ("handoff", "opted_out"):
                run_id = self.store.start_run(thread_id, policy.customer_id, "proactive")
                outcome = "skipped"
                note = f"Skipped: policy is {policy.status}, conversation is {thread['status']}."
                self.store.finish_run(run_id, 0, 0, outcome, note)
                return RunResult(run_id, thread_id, outcome, note, paused=True)
            trigger = f"EVENT renewal_due\npolicy_id={policy.id}\nexpires={policy.expiry_date}"
            return self._run(policy.customer_id, thread_id, "proactive", None, trigger)

    def handle_inbound(
        self, customer_id: int, channel: str, text: str, provider_id: str | None = None
    ) -> RunResult:
        """The customer wrote to us. Record it, apply compliance rules, then let the agent act."""
        with self.global_lock:
            store = self.store
            customer = store.get_customer(customer_id)
            if customer is None:
                raise LookupError("customer_not_found")
            if channel not in CHANNELS:
                raise ValueError(f"unknown channel: {channel}")
            policy = store.renewal_policy_for(customer_id)
            thread_id = store.open_thread(customer_id, policy.id if policy else None)
            thread = store.get_thread(thread_id)
            message_id = store.add_message(
                thread_id, customer_id, channel, "in", "customer", text,
                meta={"provider_id": provider_id} if provider_id else None,
            )
            store.mark_read_on_reply(thread_id, channel)

            if thread["status"] == "opted_out":
                if is_opt_in(text):
                    return self._opt_in(customer_id, thread_id, channel, message_id)
                return self._paused(thread_id, customer_id, "opted_out", "Customer has opted out.")
            if is_opt_out(text):
                return self._opt_out(customer_id, thread_id, channel, message_id)
            store.log_event(customer_id, channel, "replied", thread_id, message_id)
            if thread["status"] == "handoff":
                return self._paused(
                    thread_id, customer_id, "awaiting_human",
                    "A person owns this conversation; the agent is paused.",
                )
            return self._run(
                customer_id, thread_id, "inbound", channel, f"CUSTOMER_MESSAGE channel={channel}\n{text}"
            )

    def send_system(
        self,
        customer_id: int,
        thread_id: int,
        channel: str,
        body: str,
        allowed_amounts: tuple[int, ...] = (),
        kind: str = "confirmation",
    ) -> dict[str, Any]:
        """A deterministic, guardrailed message that is not model-written (e.g. a receipt)."""
        with self.global_lock:
            run_id = self.store.start_run(thread_id, customer_id, "system")
            ctx = self._ctx(customer_id, thread_id, run_id, "inbound", channel)
            ctx.allow(*allowed_amounts)
            result = self._call(ctx, "send_message", {"channel": channel, "body": body, "kind": kind})
            self.store.finish_run(
                run_id, 0, 1, "contacted" if result.get("ok") else "blocked", f"{kind} message"
            )
            return result

    # ------------------------------------------------------------------ compliance paths
    def _opt_out(self, customer_id: int, thread_id: int, channel: str, message_id: int) -> RunResult:
        store = self.store
        store.revoke_all_consents(customer_id)
        store.set_thread_status(thread_id, "opted_out")
        store.log_event(customer_id, channel, "opt_out", thread_id, message_id)
        run_id = store.start_run(thread_id, customer_id, "opt_out")
        ctx = self._ctx(customer_id, thread_id, run_id, "inbound", channel)
        ctx.exempt_consent = True  # the one confirmation we are allowed to send
        self._call(
            ctx, "send_message",
            {"channel": channel, "kind": "confirmation",
             "body": "You're unsubscribed and won't get any more renewal messages from us. "
                     "Reply START if you change your mind."},
        )
        summary = "Customer opted out. Consent revoked on all channels; no further contact."
        store.finish_run(run_id, 0, 1, "opted_out", summary)
        return RunResult(run_id, thread_id, "opted_out", summary, messages_sent=len(ctx.sent))

    def _opt_in(self, customer_id: int, thread_id: int, channel: str, message_id: int) -> RunResult:
        store = self.store
        store.set_consent(customer_id, channel, True)
        store.set_thread_status(thread_id, "open")
        store.log_event(customer_id, channel, "opt_in", thread_id, message_id)
        run_id = store.start_run(thread_id, customer_id, "opt_in")
        ctx = self._ctx(customer_id, thread_id, run_id, "inbound", channel)
        self._call(
            ctx, "send_message",
            {"channel": channel, "kind": "confirmation",
             "body": "Welcome back. You're subscribed again. Ask me anything about your renewal."},
        )
        summary = f"Customer opted back in on {channel}."
        store.finish_run(run_id, 0, 1, "opted_in", summary)
        return RunResult(run_id, thread_id, "opted_in", summary, messages_sent=len(ctx.sent))

    def _paused(self, thread_id: int, customer_id: int, outcome: str, note: str) -> RunResult:
        run_id = self.store.start_run(thread_id, customer_id, "inbound")
        self.store.finish_run(run_id, 0, 0, outcome, note)
        return RunResult(run_id, thread_id, outcome, note, paused=True)

    # ------------------------------------------------------------------ the loop
    def _ctx(
        self, customer_id: int, thread_id: int, run_id: int, trigger: str, channel: str | None
    ) -> ToolContext:
        return ToolContext(
            store=self.store, channels=self.channels, guardrails=self.guardrails,
            settings=self.settings, customer_id=customer_id, thread_id=thread_id,
            run_id=run_id, trigger=trigger, inbound_channel=channel,
        )

    def _call(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = execute_tool(ctx, name, args)
        self.store.log_tool_call(ctx.run_id, ctx.thread_id, name, args, result)
        return result

    def _history(self, thread_id: int, drop_last_inbound: bool) -> list[dict[str, Any]]:
        messages = self.store.thread_messages(thread_id)
        if drop_last_inbound and messages and messages[-1]["direction"] == "in":
            messages = messages[:-1]
        history = []
        for m in messages[-20:]:
            subject = f"Subject: {m['subject']}\n" if m["subject"] else ""
            history.append(
                {
                    "role": "user" if m["direction"] == "in" else "assistant",
                    "content": f"[{m['channel']}] {subject}{m['body']}",
                }
            )
        return history

    def _run(
        self, customer_id: int, thread_id: int, trigger: str, channel: str | None, trigger_text: str
    ) -> RunResult:
        store = self.store
        run_id = store.start_run(thread_id, customer_id, trigger)
        ctx = self._ctx(customer_id, thread_id, run_id, trigger, channel)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self._history(thread_id, drop_last_inbound=trigger == "inbound"),
            {"role": "user", "content": trigger_text},
        ]
        started = time.perf_counter()
        steps = 0
        final: str | None = None
        error: str | None = None
        try:
            for _ in range(self.settings.max_agent_steps):
                turn = self.model.respond(messages, TOOL_SPECS)
                steps += 1
                if not turn.tool_calls:
                    final = turn.text
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.text or "",
                        "tool_calls": [
                            {"id": c.id, "name": c.name, "arguments": c.arguments}
                            for c in turn.tool_calls
                        ],
                    }
                )
                for call in turn.tool_calls:
                    result = self._call(ctx, call.name, call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "name": call.name,
                            "tool_call_id": call.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                error = "Agent exceeded its step limit"
        except Exception as exc:  # the model is a dependency; its failures must degrade safely
            log.exception("agent run failed")
            error = f"Model error: {type(exc).__name__}: {exc}"

        if trigger == "inbound" and not ctx.handoff_created and (error or not ctx.sent):
            self._escalate(ctx, error or "The agent produced no reply")
            error = error or "no reply produced"

        if ctx.handoff_created:
            outcome = "handoff"
        elif error:
            outcome = "error"
        elif ctx.sent:
            outcome = "contacted" if trigger == "proactive" else "replied"
        elif ctx.scheduled:
            outcome = "scheduled"
        elif ctx.blocked:
            outcome = "blocked"
        else:
            outcome = "no_action"

        duration_ms = int((time.perf_counter() - started) * 1000)
        summary = final or error
        store.finish_run(run_id, duration_ms, steps, outcome, summary)
        return RunResult(
            run_id, thread_id, outcome, summary, messages_sent=len(ctx.sent),
            handoff=ctx.handoff_created, steps=steps, blocked=ctx.blocked,
        )

    def _escalate(self, ctx: ToolContext, reason: str) -> None:
        """Safe fallback when the agent fails: tell the customer a person will follow up."""
        if ctx.inbound_channel:
            self._call(
                ctx, "send_message",
                {"channel": ctx.inbound_channel, "kind": "handoff",
                 "body": "Thanks for your message. I've asked a colleague to follow up with "
                         "you personally."},
            )
        self._call(
            ctx, "handoff_to_human",
            {"reason": f"Automatic escalation: {reason}",
             "summary": "The assistant could not complete this request. Review the thread."},
        )
