from renewflow.analytics import kpis


def test_cohort_is_split_between_scored_and_fixed_channel(svc):
    svc.run_cohort(20, rng_seed=7)
    exp = kpis.overview(svc.store, svc.settings)["experiment"]
    arms = {a["arm"]: a for a in exp["arms"]}
    assert exp["synthetic"] is True
    assert arms["smart"]["assigned"] == arms["baseline"]["assigned"] == 10
    assert arms["smart"]["contacted"] > 0 and arms["baseline"]["contacted"] > 0


def test_control_group_is_contacted_on_the_fixed_channel(svc):
    svc.run_cohort(20, rng_seed=7)
    db = svc.store.db
    for r in db.query("SELECT key FROM settings WHERE key LIKE 'arm:%' AND value='baseline'"):
        cid = int(r["key"].split(":")[1])
        row = db.one(
            "SELECT channel FROM messages WHERE customer_id=? AND direction='out' ORDER BY id LIMIT 1", (cid,)
        )
        if row:  # quiet hours or consent can legitimately prevent a send
            assert row["channel"] == "email"


def test_reset_clears_the_experiment(svc):
    svc.run_cohort(10, rng_seed=1)
    svc.reset()
    assert all(a["assigned"] == 0 for a in kpis.overview(svc.store, svc.settings)["experiment"]["arms"])
