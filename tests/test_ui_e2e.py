"""Drives the dashboard in a real browser through the demo story. Skipped without Playwright."""

import socket
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from renewflow.api.app import create_app
from renewflow.config import Settings
from renewflow.service import RenewFlow


@pytest.fixture(scope="module")
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    svc = RenewFlow.create(Settings(db_path=":memory:"))
    server = uvicorn.Server(uvicorn.Config(create_app(svc), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    svc.store.set_setting("quiet_hours", "off")
    yield f"http://127.0.0.1:{port}", svc
    server.should_exit = True
    thread.join(5)


@pytest.fixture(scope="module")
def page(server):
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser installed in this environment
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
        yield page
        browser.close()


def test_demo_story_in_the_browser(server, page):
    base, svc = server
    page.goto(f"{base}/#/overview")
    page.wait_for_selector(".hero .figure")
    assert page.inner_text(".hero .figure").strip() == "—"  # nothing sent yet

    page.click('[data-action="open-hero"]')
    page.click('.thread-head [data-action="start"]')
    page.wait_for_selector(".msg.out")
    page.click('[data-action="side"][data-tab="play"]')
    page.click('.quick [data-text="Premium looks higher, can I split it?"]')
    page.wait_for_selector("text=4 payments of ₹4,738")
    page.click('.quick [data-text="Please email me the details"]')
    page.wait_for_selector("text=Continued on Email")
    page.click('[data-action="simtab"][data-tab="email"]')
    page.click('[data-action="open-mail"]')
    page.click(".mail-open .paybtn")
    page.click('[data-action="pay"]')
    page.wait_for_selector("text=Renewed on the quarterly plan")
    assert svc.store.get_policy(1).status == "renewed"

    page.click('.nav-item[data-view="overview"]')
    page.wait_for_function("document.querySelector('.hero .figure')?.textContent.trim() === '100%'")
    assert page.errors == []


def test_aria_state_is_exposed_when_false(server, page):
    base, _ = server
    page.goto(f"{base}/#/conversations/1")
    page.wait_for_selector(".filters")
    states = page.eval_on_selector_all(
        ".filters button", "els => els.map(e => e.getAttribute('aria-pressed'))"
    )
    assert set(states) == {"true", "false"}  # never missing or empty
    assert page.get_attribute(".switch", "aria-checked") in {"true", "false"}
