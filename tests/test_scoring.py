from renewflow.analytics import scoring


def _rank(svc, customer_id):
    return scoring.rank_channels(
        svc.store, customer_id, svc.settings.enabled_channels, svc.store.clock.now()
    )


def test_hero_prefers_whatsapp_with_high_confidence(svc):
    best, confidence = scoring.recommend(_rank(svc, 1))
    assert best.channel == "whatsapp"
    assert confidence == "high"


def test_scores_explain_themselves(svc):
    top = _rank(svc, 1)[0]
    assert top.channel == "whatsapp"
    assert any("Read 8 of 9" in r for r in top.reasons)


def test_no_consent_removes_a_channel(svc):
    svc.store.set_consent(1, "whatsapp", False)
    best, _ = scoring.recommend(_rank(svc, 1))
    assert best.channel == "email"


def test_disabled_channel_is_never_recommended(svc):
    ranked = _rank(svc, 1)
    sms = next(s for s in ranked if s.channel == "sms")
    assert sms.enabled is False and sms.eligible is False


def test_cold_start_is_neutral_and_low_confidence(svc):
    cid = svc.store.add_customer("New Person", "new@example.com", "+91 90000 99999")
    for channel in ("whatsapp", "email"):
        svc.store.set_consent(cid, channel, True)
    best, confidence = scoring.recommend(_rank(svc, cid))
    assert best.channel == "whatsapp"  # tie broken by fixed channel priority
    assert confidence == "low"


def test_recent_behaviour_outweighs_old(svc):
    store = svc.store
    cid = store.add_customer("Shift Test", "s@example.com", "+91 90000 88888")
    for channel in ("whatsapp", "email"):
        store.set_consent(cid, channel, True)
    now = store.clock.now()
    from datetime import timedelta

    from renewflow.clock import iso

    def burst(channel, days_ago, read):
        for i in range(6):
            ts = iso(now - timedelta(days=days_ago + i))
            store.log_event(cid, channel, "sent", ts=ts)
            store.log_event(cid, channel, "delivered", ts=ts)
            if read:
                store.log_event(cid, channel, "read", ts=ts)

    burst("whatsapp", 80, read=True)   # engaged long ago
    burst("email", 1, read=True)       # engaged this week
    best, _ = scoring.recommend(_rank(svc, cid))
    assert best.channel == "email"
