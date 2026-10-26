from fastapi.testclient import TestClient

from renewflow.api.app import create_app


def _client(svc) -> TestClient:
    return TestClient(create_app(svc))


def test_health_meta_and_customers(svc):
    client = _client(svc)
    assert client.get("/api/health").json() == {"ok": True}
    meta = client.get("/api/meta").json()
    assert meta["channels"] == ["whatsapp", "email"] and meta["synthetic_data"] is True
    rows = client.get("/api/customers").json()
    assert len(rows) == 40
    priya = next(r for r in rows if r["id"] == 1)
    assert priya["best_channel"] == "whatsapp" and priya["status"] == "not_contacted"


def test_customer_detail_masks_contact_details(svc):
    detail = _client(svc).get("/api/customers/1").json()
    assert "example.com" in detail["customer"]["email"] and "priya" not in detail["customer"]["email"]
    assert "•" in detail["customer"]["phone"]
    assert detail["channels"]["recommended"] == "whatsapp"
    assert detail["policy"]["delta"] == 3600
    assert _client(svc).get("/api/customers/9999").status_code == 404


def test_conversation_flow_over_http(svc):
    client = _client(svc)
    started = client.post("/api/renewals/1/start").json()
    assert started["outcome"] == "contacted"
    reply = client.post(
        "/api/simulator/reply",
        json={"customer_id": 1, "channel": "whatsapp", "text": "Can I pay quarterly?"},
    ).json()
    assert reply["outcome"] == "replied"
    detail = client.get("/api/customers/1").json()
    assert [m["direction"] for m in detail["messages"]] == ["out", "in", "out"]
    assert detail["messages"][0]["read"] is True  # replying implies the first message was read
    assert detail["trace"][-1]["tool_calls"][-1]["name"] == "send_message"

    bad = client.post("/api/simulator/reply", json={"customer_id": 1, "channel": "pager", "text": "hi"})
    assert bad.status_code == 400
    assert client.post("/api/simulator/reply", json={"customer_id": 1, "channel": "email", "text": ""}).status_code == 422


def test_payment_page_and_confirmation(svc):
    client = _client(svc)
    client.post("/api/renewals/1/start")
    client.post("/api/simulator/reply", json={"customer_id": 1, "channel": "whatsapp", "text": "send the payment link"})
    token = svc.store.latest_quote(1).token
    page = client.get(f"/pay/{token}")
    assert page.status_code == 200 and "Pay now" in page.text
    done = client.post(f"/pay/{token}")
    assert "Payment received" in done.text
    assert svc.store.get_policy(1).status == "renewed"
    assert "Link not found" in client.get("/pay/not-a-token").text


def test_overview_cohort_and_reset(svc):
    client = _client(svc)
    assert client.post("/api/simulator/cohort", json={"count": 10}).json()["customers"] == 10
    overview = client.get("/api/overview").json()
    assert overview["kpis"]["contacted"] >= 7 and overview["activity"]
    assert client.post("/api/reset").json() == {"ok": True}
    assert client.get("/api/overview").json()["kpis"]["contacted"] == 0


def test_settings_toggle_and_version_counter(svc):
    client = _client(svc)
    before = client.get("/api/version").json()["version"]
    assert client.post("/api/settings", json={"quiet_hours": "off"}).json()["quiet_hours"] == "off"
    assert client.get("/api/version").json()["version"] > before
    assert client.post("/api/settings", json={"quiet_hours": "maybe"}).status_code == 422


def test_dashboard_assets_are_served(svc):
    client = _client(svc)
    index = client.get("/")
    assert index.status_code == 200 and "RenewFlow" in index.text
    for path in ("/app.js", "/styles.css", "/fonts/figtree-latin-wght-normal.woff2"):
        assert client.get(path).status_code == 200, path
