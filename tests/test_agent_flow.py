from conftest import outbound

from renewflow.agent.tools import execute_tool
from renewflow.analytics import kpis
from renewflow.llm.base import ChatModel


def test_priya_demo_story_end_to_end(svc):
    store = svc.store

    # 1. Proactive: best channel is WhatsApp, and the figures come from the policy.
    first = svc.start_renewal(1)
    assert first.outcome == "contacted"
    opener = outbound(svc, first.thread_id)[0]
    assert opener["channel"] == "whatsapp"
    assert "₹18,400" in opener["body"] and "₹14,800" in opener["body"]
    assert "virtual renewal assistant" in opener["body"]  # discloses it is automated
    assert len(store.followups_for(1)) == 1

    # 2. She asks to split the payment: explanation + a priced quarterly option.
    second = svc.inbound(1, "whatsapp", "Premium looks higher, can I split it?")
    assert second.outcome == "replied"
    reply = outbound(svc, first.thread_id)[-1]["body"]
    assert "Vehicle value recalculated" in reply
    assert "4 payments of ₹4,738" in reply and "₹18,952" in reply and "₹552" in reply
    assert store.latest_quote(1).plan == "quarterly"

    # 3. She asks for details by email: the thread moves channel without losing context.
    svc.inbound(1, "whatsapp", "Please email me the details")
    messages = outbound(svc, first.thread_id)
    email = next(m for m in messages if m["channel"] == "email")
    assert "Renew securely:" in email["body"] and "₹4,738" in email["body"]
    assert email["subject"]
    ack = messages[-1]
    assert ack["channel"] == "whatsapp" and "emailed the quote" in ack["body"]
    assert {m["channel"] for m in store.thread_messages(first.thread_id)} == {"whatsapp", "email"}
    assert len({m["thread_id"] for m in store.thread_messages(first.thread_id)}) == 1

    # 4. She pays from the emailed link: renewed, receipt sent, KPIs move.
    token = store.latest_quote(1).token
    assert store.has_event(email["id"], "clicked") is False
    paid = svc.pay(token)
    assert paid["ok"] and paid["amount"] == 18952
    assert store.get_policy(1).status == "renewed"
    assert store.get_thread(first.thread_id)["status"] == "renewed"
    assert store.has_event(email["id"], "clicked")
    receipt = outbound(svc, first.thread_id)[-1]
    assert "Payment received" in receipt["body"] and "quarterly plan" in receipt["body"]
    assert svc.pay(token).get("already_renewed")  # paying twice is harmless

    overview = kpis.overview(store, svc.settings)["kpis"]
    assert overview["renewed"] == 1 and overview["revenue_secured"] == 18952
    assert overview["cross_channel_threads"] == 1
    assert overview["handled_without_human"] == 1.0


def test_every_tool_call_is_traced(svc):
    result = svc.start_renewal(1)
    trace = svc.store.trace_for_thread(result.thread_id)
    names = [c["name"] for c in trace[0]["tool_calls"]]
    assert names == ["next_best_channel", "lookup_policy", "send_message", "schedule_followup"]
    assert trace[0]["outcome"] == "contacted"


def test_claims_and_complaints_go_to_a_person(svc):
    first = svc.start_renewal(1)
    result = svc.inbound(1, "whatsapp", "My claim was rejected and I want to speak to a person")
    assert result.outcome == "handoff" and result.handoff
    thread = svc.store.get_thread(first.thread_id)
    assert thread["status"] == "handoff"
    handoff = svc.store.list_handoffs()[0]
    assert handoff["status"] == "open" and "claim" in handoff["summary"].lower()
    assert "colleague" in outbound(svc, first.thread_id)[-1]["body"]

    # While a person owns the thread the agent stays silent.
    sent_before = len(outbound(svc, first.thread_id))
    paused = svc.inbound(1, "whatsapp", "Hello? Anyone there?")
    assert paused.outcome == "awaiting_human" and paused.paused
    assert len(outbound(svc, first.thread_id)) == sent_before

    svc.resolve_handoff(handoff["id"], "Called customer")
    assert svc.store.get_thread(first.thread_id)["status"] == "open"


def test_no_claim_bonus_is_not_mistaken_for_a_claim(svc):
    svc.start_renewal(1)
    result = svc.inbound(1, "whatsapp", "why did my no claim bonus drop")
    assert result.outcome == "replied" and not result.handoff


def test_stop_revokes_consent_and_is_honoured(svc):
    first = svc.start_renewal(1)
    result = svc.inbound(1, "whatsapp", "STOP")
    assert result.outcome == "opted_out"
    assert not any(svc.store.consents(1).values())
    assert svc.store.get_thread(first.thread_id)["status"] == "opted_out"
    assert "unsubscribed" in outbound(svc, first.thread_id)[-1]["body"]

    # No more proactive contact, and further messages get no agent reply.
    assert svc.start_renewal(1).outcome == "skipped"
    sent = len(outbound(svc, first.thread_id))
    svc.inbound(1, "whatsapp", "hello?")
    assert len(outbound(svc, first.thread_id)) == sent

    svc.inbound(1, "whatsapp", "START")
    assert svc.store.consents(1)["whatsapp"] is True
    assert svc.store.get_thread(first.thread_id)["status"] == "open"


def test_unclear_messages_are_clarified_once_then_escalated(svc):
    first = svc.start_renewal(1)
    one = svc.inbound(1, "whatsapp", "hmm what is this about")
    assert one.outcome == "replied" and not one.handoff
    two = svc.inbound(1, "whatsapp", "no idea what this is")
    assert two.outcome == "handoff"
    assert svc.store.get_thread(first.thread_id)["status"] == "handoff"


def test_tools_cannot_read_another_customers_policy(svc):
    thread_id = svc.store.open_thread(1)
    ctx = svc.agent._ctx(1, thread_id, run_id=0, trigger="inbound", channel="whatsapp")
    other = svc.store.renewal_policy_for(2)
    result = execute_tool(ctx, "lookup_policy", {"policy_id": other.id})
    assert result == {"ok": False, "error": "policy_not_found"}


def test_bad_tool_arguments_become_results_not_crashes(svc):
    thread_id = svc.store.open_thread(1)
    ctx = svc.agent._ctx(1, thread_id, run_id=0, trigger="inbound", channel="whatsapp")
    assert execute_tool(ctx, "nope", {})["ok"] is False
    assert "missing arguments" in execute_tool(ctx, "send_message", {})["error"]
    assert execute_tool(ctx, "generate_quote", {"plan": "weekly"})["ok"] is False


def test_model_failure_degrades_to_a_human_handoff(svc):
    class Broken:
        name = "broken"

        def respond(self, messages, tools):
            raise RuntimeError("model unavailable")

    svc.start_renewal(1)
    svc.agent.model = Broken()  # type: ignore[assignment]
    result = svc.inbound(1, "whatsapp", "Why is my premium higher?")
    assert result.outcome == "handoff"
    thread = svc.store.thread_for(1)
    assert "colleague" in outbound(svc, thread["id"])[-1]["body"]
    assert svc.store.list_handoffs()[0]["reason"].startswith("Automatic escalation")


def test_runaway_model_is_stopped_by_the_step_limit(svc):
    from renewflow.llm.base import ModelTurn, ToolCall

    class Loop:
        name = "loop"

        def respond(self, messages, tools):
            return ModelTurn(None, [ToolCall("x", "lookup_policy", {})])

    svc.start_renewal(1)
    svc.agent.model = Loop()  # type: ignore[assignment]
    result = svc.inbound(1, "whatsapp", "hello")
    assert result.outcome == "handoff"
    assert result.steps == svc.settings.max_agent_steps


def test_cohort_simulation_runs_the_real_agent(svc):
    summary = svc.run_cohort(20, rng_seed=3)
    assert summary["customers"] == 20
    assert svc.store.thread_for(1) is None  # the demo customer is left untouched

    data = kpis.overview(svc.store, svc.settings)
    counts = [step["count"] for step in data["funnel"]]
    assert counts == sorted(counts, reverse=True)  # the funnel can only narrow
    assert data["kpis"]["contacted"] >= 15
    assert data["guardrails"]["by_reason"].get("ungrounded_amount", 0) == 0

    now = svc.store.now_iso()
    assert all(m["created_at"] <= now for m in svc.store.db.query("SELECT created_at FROM messages"))


def test_chat_model_protocol_is_satisfied_by_the_mock(svc):
    model: ChatModel = svc.model
    assert model.name


def test_cancel_discount_and_already_paid_go_to_a_person(svc):
    for cid, text in [(1, "I already renewed last week"), (2, "Can you give me a discount?"),
                      (3, "I want to cancel my policy")]:
        svc.start_renewal(cid)
        assert svc.inbound(cid, "whatsapp", text).outcome == "handoff"


def test_bare_ok_does_not_send_a_payment_link(svc):
    first = svc.start_renewal(1)
    svc.inbound(1, "whatsapp", "ok")
    last = outbound(svc, first.thread_id)[-1]["body"]
    assert "payment link" in last and "http" not in last
    assert svc.store.latest_quote(1) is None
    # and it did not use up the one clarification
    assert svc.inbound(1, "whatsapp", "hmm what is this about").outcome == "replied"


def test_premium_question_is_answered_from_the_policy(svc):
    first = svc.start_renewal(1)
    svc.inbound(1, "whatsapp", "how much is it?")
    assert "₹18,400" in outbound(svc, first.thread_id)[-1]["body"]
