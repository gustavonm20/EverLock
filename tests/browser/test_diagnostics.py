"""Critical diagnostics journeys; run explicitly with pytest tests/browser."""

import re

from conftest import PASSWORD
from playwright.sync_api import expect

from everlock.mailer import MailSettings


def login(page, username="admin"):
    page.goto("/")
    expect(page.locator("#auth-panel")).to_be_visible()
    page.locator("#identifier").fill(username)
    page.locator("#login-password").fill(PASSWORD)
    page.locator("#auth-submit").click()
    expect(page.locator("body")).to_have_attribute(
        "data-role", "admin" if username == "admin" else "user",
    )
    expect(page.locator("#auth-panel")).to_be_hidden()


def open_diagnostics(page):
    with page.expect_response("**/api/diagnostics") as response:
        page.locator('a.nav-link[href="#diagnostico"]').click()
    assert response.value.status == 200
    payload = response.value.json()
    expect(page.locator("#diagnostics-checks .diagnostic-card")).to_have_count(
        len(payload["checks"]),
    )
    return payload


def test_admin_opens_diagnostics_and_refreshes_live_state(page, local_server):
    login(page)
    initial = open_diagnostics(page)
    expect(page.locator("#diagnostics-title")).to_be_visible()
    expect(page.locator("#diagnostics-checked-at")).not_to_have_text("")
    assert initial["mode"] == "simulation"
    for check in initial["checks"]:
        card = page.locator(f'.diagnostic-card[data-check="{check["id"]}"]')
        expect(card).to_contain_text(check["title"])
        expect(card).to_contain_text(check["summary"])

    # The next GET must really run: change a local service without touching the UI.
    with local_server.app.state.controller.mutex:
        local_server.app.state.mailer.settings = MailSettings(
            "smtp.example.invalid", 587, "ficticio", "Nao e uma credencial1!",
            "testes@example.invalid",
        )
    with page.expect_response("**/api/diagnostics") as refreshed:
        page.locator("#diagnostics-refresh").click()
    assert refreshed.value.status == 200
    expect(page.locator("#diagnostics-refresh")).to_be_enabled()
    updated = refreshed.value.json()
    initial_email = next(check for check in initial["checks"] if check["id"] == "email")
    updated_email = next(check for check in updated["checks"] if check["id"] == "email")
    assert initial_email["summary"] != updated_email["summary"]
    for check in updated["checks"]:
        expect(page.locator(f'.diagnostic-card[data-check="{check["id"]}"]')).to_contain_text(
            check["summary"],
        )


def test_regular_user_cannot_open_admin_diagnostics_even_by_hash(page):
    login(page, "visitante")
    expect(page.locator('a.nav-link[href="#diagnostico"]')).to_be_hidden()
    page.evaluate("location.hash = '#diagnostico'")
    expect(page).to_have_url(re.compile(r"#simulador$"))
    expect(page.locator("#diagnostico")).to_be_hidden()
    expect(page.locator("#diagnostics-checks")).to_be_empty()
    assert page.request.get("/api/diagnostics").status == 403


def test_expired_session_clears_diagnostics_and_returns_to_login(page, local_server):
    login(page)
    open_diagnostics(page)
    # Expire only after the click has issued its request. Background panels also
    # detect expiry; expiring before the click lets them hide the button first.
    # Continue to the real endpoint: the asserted 401 is not a mocked response.
    def expire_before_diagnostics(route):
        local_server.expire_sessions()
        route.continue_()

    page.route("**/api/diagnostics", expire_before_diagnostics, times=1)
    with page.expect_response("**/api/diagnostics") as expired:
        page.locator("#diagnostics-refresh").click()
    assert expired.value.status == 401
    expect(page.locator("#auth-panel")).to_be_visible()
    expect(page.locator("#main")).to_be_hidden()
    expect(page.locator("#diagnostics-checks")).to_be_empty()
    expect(page.locator('a.nav-link[href="#diagnostico"]')).to_be_hidden()


def test_late_diagnostics_cannot_restore_data_after_navigation_or_logout(page):
    login(page)
    payload = open_diagnostics(page)
    payload["checks"][0]["summary"] = "RESULTADO ANTIGO QUE NÃO DEVE REAPARECER"
    # Delay delivery after a genuine endpoint response. This deliberately ignores abort,
    # exercising the generation guard even when a response was already received.
    delay_next_response = """(payload) => {
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        if (String(args[0]) !== '/api/diagnostics') return response;
        window.fetch = originalFetch;
        return new Promise((resolve) => {
          window.releaseOldDiagnostics = () => resolve(new Response(JSON.stringify(payload), {
            status: 200, headers: {'Content-Type': 'application/json'}
          }));
          document.body.dataset.testPendingDiagnostics = 'true';
        });
      };
    }"""
    for departure in ("navigation", "logout"):
        page.evaluate(delay_next_response, payload)
        page.locator("#diagnostics-refresh").click()
        expect(page.locator("body")).to_have_attribute("data-test-pending-diagnostics", "true")
        if departure == "navigation":
            page.locator('a.nav-link[href="#simulador"]').click()
            expect(page).to_have_url(re.compile(r"#simulador$"))
        else:
            page.locator("#logout").click()
            expect(page.locator("#auth-panel")).to_be_visible()
        page.evaluate("""async () => {
          window.releaseOldDiagnostics();
          delete window.releaseOldDiagnostics;
          delete document.body.dataset.testPendingDiagnostics;
          await new Promise(requestAnimationFrame);
        }""")
        expect(page.locator("#diagnostics-checks")).to_be_empty()
        expect(page.locator("#diagnostics-checks")).not_to_contain_text(
            "RESULTADO ANTIGO QUE NÃO DEVE REAPARECER",
        )
        if departure == "navigation":
            open_diagnostics(page)
