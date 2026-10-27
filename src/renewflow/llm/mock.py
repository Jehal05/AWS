"""A deterministic, offline stand-in for the LLM.

It speaks the same tool-calling protocol as a real model: it looks at the conversation,
asks for tools one step at a time, and writes messages only from numbers the tools returned.
That keeps the whole system runnable and testable without any model access, and lets the
guardrails be exercised for real. On AWS the Bedrock adapter replaces it.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from ..pricing import inr
from .base import ModelTurn, ToolCall

PLAN_LABEL = {"annual": "annual", "quarterly": "quarterly", "monthly": "monthly"}


def classify(text: str) -> list[str]:
    """Rule-based intent detection. Returns intents in the order they were found."""
    t = re.sub(r"no[- ]claims?( bonus)?", " ", text.lower())
    if re.search(r"\b(stop|unsubscribe|opt[- ]?out)\b|mat bhej|bhejna band|message band|band karo", t) \
            or any(w in t for w in ("बंद करो", "मत भेजो", "मैसेज बंद")):
        return ["opt_out"]
    if re.search(
        r"\b(claims?|complain\w*|disput\w*|lawyer|legal|ombudsman|human|agent|person|"
        r"representative|call me|speak to|talk to|manager|refund|cancel\w*|discount|"
        r"negotiat\w*|guarantee\w*|scam|fraud\w*|cheat\w*|already (renewed|paid|bought))\b",
        t,
    ):
        return ["handoff"]
    # Devanagari: \\b is unreliable around combining marks, so match substrings.
    if any(w in t for w in ("व्यक्ति", "इंसान", "बात करनी", "शिकायत", "क्लेम", "कैंसिल", "रद्द")):
        return ["handoff"]
    intents: list[str] = []
    if re.search(r"\b(e-?mail|mail me|send (me )?(the |a )?(details|quote|summary|brochure))\b", t):
        intents.append("details_email")
    if re.search(r"\b(quarter\w*|month\w*|instal+ments?|emi|split|spread)\b", t) or "in parts" in t:
        intents.append("split")
    if re.search(r"\b(why|higher|increase\w*|gone up|expensive|too (high|much)|hike|costly)\b", t):
        intents.append("premium_why")
    if re.search(r"\b(how much|what is (the|my) (premium|price|amount)|premium amount)\b", t):
        intents.append("facts")
    if re.search(r"\b(pay|renew\w*|link|proceed|go ahead|confirm)\b", t):
        intents.append("pay")
    elif not intents and re.fullmatch(r"\W*(yes|yeah|yep|ok|okay|sure|k|fine)\W*", t):
        intents.append("ack")
    if not intents and any(w in t for w in ("प्रीमियम", "क्यों", "बढ़", "कितना")):
        intents.append("premium_why")
    # Common Hinglish: treat as a premium question rather than an unknown message.
    if not intents and re.search(r"\b(kitna|kyun|kyu|badh\w*|mehenga|mahanga|premium)\b", t):
        intents.append("premium_why")
    if not intents:
        intents.append("greet" if re.match(r"\s*(hi|hello|hey|namaste)\b", t) else "unknown")
    return intents


def _primary(intents: list[str]) -> str:
    for key in ("opt_out", "handoff", "details_email"):
        if key in intents:
            return key
    if "split" in intents or "premium_why" in intents:
        return "explain"
    return intents[0]


def _date(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return f"{d.day} {d.strftime('%b %Y')}"


def _signed(amount: int) -> str:
    return f"+{inr(amount)}" if amount >= 0 else inr(amount)


def _plan_phrase(q: dict[str, Any]) -> str:
    if q["installments"] == 1:
        return inr(q["total"])
    return f"{q['installments']} × {inr(q['per_installment'])}"


class _Run:
    """Everything the model can see about the current run."""

    def __init__(self, head: str, done: dict[str, list[dict[str, Any]]]):
        self.head = head
        self.done = done

    def n(self, tool: str) -> int:
        return len(self.done.get(tool, []))

    def last(self, tool: str) -> dict[str, Any] | None:
        results = self.done.get(tool)
        return results[-1] if results else None

    def call(self, name: str, **arguments: Any) -> ModelTurn:
        arguments = {k: v for k, v in arguments.items() if v is not None}
        return ModelTurn(None, [ToolCall(f"{name}-{self.n(name) + 1}", name, arguments)])

    def send(self, channel: str, body: str, subject: str | None = None, kind: str = "info"):
        return self.call(
            "send_message", channel=channel, body=body, subject=subject, kind=kind
        )

    @staticmethod
    def finish(text: str) -> ModelTurn:
        return ModelTurn(text, [])


CHANNEL_NAMES = {"whatsapp": "WhatsApp", "email": "email", "sms": "SMS"}


class MockModel:
    name = "mock-rules-v1"

    def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        done: dict[str, list[dict[str, Any]]] = {}
        for m in messages[last_user + 1 :]:
            if m["role"] == "tool":
                done.setdefault(m["name"], []).append(json.loads(m["content"]))
        run = _Run(messages[last_user]["content"], done)
        if run.head.startswith("EVENT renewal_due"):
            return self._proactive(run)
        return self._inbound(run)

    # ------------------------------------------------------------------ proactive
    def _proactive(self, run: _Run) -> ModelTurn:
        if run.n("next_best_channel") == 0:
            return run.call("next_best_channel")
        best = run.last("next_best_channel") or {}
        if run.n("lookup_policy") == 0:
            return run.call("lookup_policy")
        pol = run.last("lookup_policy") or {}
        if not pol.get("ok", True):
            return run.finish("Policy not found; nothing sent.")
        if pol["status"] != "open":
            return run.finish("Policy is already renewed; skipped.")
        channel = best.get("recommended")
        if channel is None:
            return run.finish("No channel with consent is available; skipped.")
        quiet = best["quiet_hours"]
        if quiet["active"]:
            if run.n("schedule_followup") == 0:
                return run.call(
                    "schedule_followup",
                    hours=max(1, int(quiet["hours_until_window"])),
                    channel=channel,
                    note="Send the renewal message when quiet hours end.",
                )
            return run.finish(f"Quiet hours are active; scheduled a follow-up on {CHANNEL_NAMES.get(channel, channel)}.")
        if run.n("send_message") == 0:
            subject, body = self._intro(pol, channel)
            return run.send(channel, body, subject, kind="proactive")
        sent = run.last("send_message") or {}
        if not sent.get("ok"):
            why = sent.get("blocked_by") or sent.get("error")
            return run.finish(f"Could not send on {CHANNEL_NAMES.get(channel, channel)}: {why}.")
        if run.n("schedule_followup") == 0:
            return run.call(
                "schedule_followup",
                hours=48,
                channel=best.get("fallback") or channel,
                note="Follow up if there is no reply.",
            )
        return run.finish(
            f"Sent the renewal message on {CHANNEL_NAMES.get(channel, channel)} (confidence: {best['confidence']}) "
            "and scheduled a follow-up in 48 hours."
        )

    # ------------------------------------------------------------------ inbound
    def _inbound(self, run: _Run) -> ModelTurn:
        first_line, _, text = run.head.partition("\n")
        channel = first_line.split("channel=", 1)[-1].strip()
        intents = classify(text)
        primary = _primary(intents)

        if run.n("lookup_policy") == 0:
            return run.call("lookup_policy")
        pol = run.last("lookup_policy") or {}
        if not pol.get("ok", True):
            return self._handoff(run, channel, pol, text, "Policy could not be found for this customer.")

        if pol["status"] == "renewed" and primary != "handoff":
            if run.n("send_message") == 0:
                return run.send(
                    channel,
                    f"Your {pol['product']} is already renewed, so there's nothing more to do. "
                    "Thank you!",
                )
            return run.finish("Customer already renewed; confirmed.")

        if primary == "handoff":
            return self._handoff(run, channel, pol, text, "Customer asked for a person or raised a "
                                 "claim, complaint or dispute.")
        if primary == "explain":
            return self._explain(run, channel, pol, text, intents)
        if primary == "details_email":
            return self._details_email(run, channel, pol, text)
        if primary == "pay":
            return self._pay(run, channel, pol)
        if primary == "facts":
            return self._facts(run, channel, pol)
        if primary == "ack":
            if run.n("send_message") == 0:
                return run.send(
                    channel,
                    "Would you like me to send your secure payment link, or explain the premium "
                    "or set up instalments first?",
                    kind="info",
                )
            return run.finish("Asked the customer what they would like to do.")
        # greet / unknown
        if pol["clarifications_sent"] >= 1:
            return self._handoff(run, channel, pol, text,
                                 "Assistant could not understand the request after two attempts.")
        if run.n("send_message") == 0:
            return run.send(
                channel,
                "Thanks for your message. I can explain why your premium changed, set up "
                "instalments, email you the quote, or send a payment link. Which would you like?",
                kind="clarify",
            )
        return run.finish("Asked the customer to clarify.")

    def _explain(self, run, channel, pol, text, intents):
        wants_split = "split" in intents
        if wants_split and run.n("generate_quote") == 0:
            plan = "monthly" if "month" in text.lower() else "quarterly"
            return run.call("generate_quote", plan=plan)
        if run.n("send_message") > 0:
            return run.finish("Explained the premium and offered payment options.")
        parts: list[str] = []
        if "premium_why" in intents or not wants_split:
            parts.append(self._why(pol))
        if wants_split:
            q = run.last("generate_quote") or {}
            if q.get("ok"):
                parts.append(
                    f"Here's the {PLAN_LABEL[q['plan']]} option: {q['installments']} payments of "
                    f"{inr(q['per_installment'])} (total {inr(q['total'])}). That includes "
                    f"{inr(q['surcharge'])} for paying in instalments, compared with "
                    f"{inr(pol['premium_new'])} upfront.\n\nShall I email you the quote with a "
                    "payment link, or send the link here?"
                )
            else:
                parts.append("I couldn't set up that payment plan just now.")
        else:
            parts.append("Would you like to see instalment options?")
        return run.send(channel, "\n\n".join(parts), kind="quote" if wants_split else "info")

    @staticmethod
    def _why(pol: dict[str, Any]) -> str:
        if pol["delta"] == 0:
            return f"Your premium is unchanged at {inr(pol['premium_new'])}."
        lines = [
            f"Your premium moved from {inr(pol['premium_prev'])} to {inr(pol['premium_new'])} "
            f"({_signed(pol['delta'])}). Here's what changed:"
        ]
        lines += [f"• {r['label']}: {_signed(r['amount'])}" for r in pol["increase_reasons"]]
        return "\n".join(lines)

    def _details_email(self, run, channel, pol, text):
        quote = run.last("generate_quote") or pol.get("latest_quote")
        if quote is None:
            if run.n("generate_quote") == 0:
                return run.call("generate_quote", plan="annual")
            return run.finish("Could not prepare a quote.")
        sends = run.done.get("send_message", [])
        email_ok = pol["consents"].get("email") and pol.get("email_masked")
        if not sends:
            if email_ok:
                subject = f"Your renewal quote: {pol['product']}"
                body = (
                    f"Hello {pol['first_name']},\n\nHere is your renewal summary for "
                    f"{pol['asset']} (policy {pol['policy_number']}).\n\n"
                    f"Plan: {PLAN_LABEL[quote['plan']].capitalize()} ({_plan_phrase(quote)})\n"
                    f"Total: {inr(quote['total'])}\nExpires: {_date(pol['expiry_date'])}\n\n"
                    f"Renew securely: {quote['link']}\n\nIf anything looks off, reply to this "
                    "email and I'll help.\n\n— Your virtual renewal assistant"
                )
                return run.send("email", body, subject, kind="quote")
            return run.send(
                channel,
                f"I can't email you because there is no email consent on file. Here's your "
                f"payment link instead ({_plan_phrase(quote)}): {quote['link']}",
                kind="quote",
            )
        if len(sends) == 1:
            if sends[0].get("ok") and channel != "email" and email_ok:
                return run.send(
                    channel,
                    f"Done. I've emailed the quote to {pol['email_masked']}. Reply here if you "
                    "have any questions.",
                )
            if not sends[0].get("ok") and email_ok:
                return run.send(
                    channel,
                    f"I couldn't send the email, so here's your payment link "
                    f"({_plan_phrase(quote)}): {quote['link']}",
                    kind="quote",
                )
        return run.finish("Emailed the quote and confirmed on the original channel.")

    def _facts(self, run, channel, pol):
        if run.n("send_message") == 0:
            return run.send(
                channel,
                f"Your renewal premium for the {pol['product']} is {inr(pol['premium_new'])} "
                f"(last year: {inr(pol['premium_prev'])}). It expires on "
                f"{_date(pol['expiry_date'])}. I can explain the change, set up instalments, or "
                "send a payment link.",
                kind="info",
            )
        return run.finish("Answered the premium question.")

    def _pay(self, run, channel, pol):
        quote = run.last("generate_quote") or pol.get("latest_quote")
        if quote is None:
            if run.n("generate_quote") == 0:
                return run.call("generate_quote", plan="annual")
            return run.finish("Could not prepare a payment link.")
        if run.n("send_message") == 0:
            return run.send(
                channel,
                f"Great, here's your secure payment link for the {PLAN_LABEL[quote['plan']]} plan "
                f"({_plan_phrase(quote)}): {quote['link']}\nThe link works until your policy "
                f"expires on {_date(pol['expiry_date'])}.",
                kind="quote",
            )
        return run.finish("Sent the payment link.")

    def _handoff(self, run, channel, pol, text, reason):
        if run.n("send_message") == 0:
            return run.send(
                channel,
                "I'm sorry about that, and I want to get it right. I've asked a colleague to "
                "contact you. They'll have this conversation in front of them, so you won't need "
                "to repeat yourself.",
                kind="handoff",
            )
        if run.n("handoff_to_human") == 0:
            clipped = text.strip().replace("\n", " ")[:200]
            summary = (
                f'Customer wrote: "{clipped}". Renewal due {_date(pol["expiry_date"])}'
                if pol.get("expiry_date")
                else f'Customer wrote: "{clipped}".'
            )
            return run.call("handoff_to_human", reason=reason, summary=summary)
        return run.finish("Handed over to a human with a summary.")

    # ------------------------------------------------------------------ copy
    @staticmethod
    def _intro(pol: dict[str, Any], channel: str) -> tuple[str | None, str]:
        days = pol["days_to_expiry"]
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        core = (
            f"Your {pol['product']} for {pol['asset']} expires {when} "
            f"({_date(pol['expiry_date'])}).\n\nYour renewal premium is "
            f"{inr(pol['premium_new'])} (last year: {inr(pol['premium_prev'])}). I can explain "
            "what changed, set up instalments, or email you the full quote. Just reply here."
        )
        if channel == "email":
            return (
                f"Your {pol['product']} renews on {_date(pol['expiry_date'])}",
                f"Hello {pol['first_name']},\n\nI'm your virtual renewal assistant. {core}\n\n"
                "— Your virtual renewal assistant",
            )
        return None, f"Hi {pol['first_name']}, I'm your virtual renewal assistant. {core}"
