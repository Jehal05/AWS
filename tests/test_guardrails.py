from conftest import NIGHT_IST, outbound


def _system_send(svc, body, channel="whatsapp", amounts=()):
    thread_id = svc.store.open_thread(1)
    return svc.agent.send_system(1, thread_id, channel, body, allowed_amounts=amounts)


def test_ungrounded_amounts_are_blocked(svc):
    result = _system_send(svc, "Your premium is only ₹99,999 today")
    assert result["ok"] is False and result["blocked_by"] == "ungrounded_amount"


def test_grounded_amounts_pass(svc):
    result = _system_send(svc, "Your premium is ₹18,400", amounts=(18400,))
    assert result["ok"] is True


def test_missing_consent_blocks_send(svc):
    svc.store.set_consent(1, "whatsapp", False)
    result = _system_send(svc, "Hello")
    assert result["blocked_by"] == "no_consent"


def test_prohibited_promises_are_blocked(svc):
    result = _system_send(svc, "We guarantee your claim will be approved")
    assert result["blocked_by"] == "prohibited_claim"


def test_over_long_message_is_blocked(svc):
    result = _system_send(svc, "x" * 1001)
    assert result["blocked_by"] == "too_long"


def test_disabled_channel_is_blocked(svc):
    result = _system_send(svc, "Hello", channel="sms")
    assert result["blocked_by"] == "channel_unavailable"


def test_quiet_hours_defer_proactive_messages(svc, clock):
    clock.set(NIGHT_IST)  # 23:00 for the customer
    result = svc.start_renewal(1)
    assert result.outcome == "scheduled"
    assert result.messages_sent == 0
    followups = svc.store.followups_for(1)
    assert len(followups) == 1 and "quiet hours" in followups[0]["note"].lower()


def test_quiet_hours_can_be_switched_off_for_demos(svc, clock):
    clock.set(NIGHT_IST)
    svc.store.set_setting("quiet_hours", "off")
    assert svc.start_renewal(1).outcome == "contacted"


def test_replies_are_allowed_at_night(svc, clock):
    svc.start_renewal(1)
    clock.set(NIGHT_IST)
    result = svc.inbound(1, "whatsapp", "Why has my premium gone up?")
    assert result.outcome == "replied"


def test_proactive_rate_limit(svc):
    assert svc.start_renewal(1).outcome == "contacted"
    assert svc.start_renewal(1).outcome == "contacted"
    third = svc.start_renewal(1)
    assert third.outcome == "blocked"
    assert third.blocked[0]["reason"] == "rate_limit"
    thread = svc.store.thread_for(1)
    assert len(outbound(svc, thread["id"])) == 2
