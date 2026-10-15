"""Synthetic UI checks for navigation, history races and consent before camera."""

from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect
from test_diagnostics import login

from everlock.identities import CONSENT_VERSION


def navigate(page, section):
    menu = page.locator("#nav-toggle")
    if menu.is_visible():
        menu.click()
    page.locator(f'a.nav-link[href="#{section}"]').click()
    expect(page.locator(f"#{section}")).to_be_visible()


def test_navigation_keyboard_and_layout_on_desktop_and_mobile(page, tmp_path):
    login(page)
    for width, height in ((1440, 1000), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        for section in ("simulador", "identidades", "diagnostico"):
            navigate(page, section)
            expect(page.locator("#nav-toggle")).to_have_attribute("aria-expanded", "false")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            ), f"Rolagem horizontal em {section}, largura {width}"
            page.screenshot(path=str(tmp_path / f"{section}-{width}.png"), full_page=True)
        if width == 390:
            page.locator("#nav-toggle").click()
            expect(page.locator("#navigation")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator("#navigation")).to_be_hidden()
            expect(page.locator("#nav-toggle")).to_be_focused()
            page.locator("#theme-toggle").click()
            page.screenshot(path=str(tmp_path / "configuracao-mobile-tema.png"), full_page=True)


def test_history_does_not_reuse_page_cursor_after_failed_filter(page):
    login(page)

    def history(route):
        query = parse_qs(urlsplit(route.request.url).query)
        if query.get("outcome") == ["denied"]:
            route.fulfill(status=500, json={"detail": "Falha sintética"})
            return
        older = "before_id" in query
        route.fulfill(json={
            "items": [{
                "id": 9 if older else 10, "type": "test", "title": "Evento sintético",
                "detail": "Dados de teste", "source": "system", "outcome": "info",
                "actor": None, "simulated_at": 0, "created_at": "2026-10-01T12:00:00Z",
            }],
            "next_cursor": None if older else 10, "has_more": not older,
        })

    page.route("**/api/events?*", history)
    navigate(page, "atividade")
    expect(page.locator("#history-more")).to_be_enabled()
    page.locator('#history-filter [name="outcome"]').select_option("denied")
    page.locator('#history-filter button[type="submit"]').click()
    expect(page.locator("#history-note")).to_contain_text("Não foi possível carregar")
    expect(page.locator("#history-more")).to_be_hidden()
    page.locator("#history-clear").click()
    expect(page.locator("#history-more")).to_be_enabled()
    page.locator("#history-more").click()
    expect(page.locator("#events .event-item")).to_have_count(2)
    expect(page.locator("#history-more")).to_be_hidden()


def test_history_filter_edit_discards_late_export_cursor(page):
    login(page)
    navigate(page, "atividade")
    expect(page.locator("#history-refresh")).to_be_enabled()
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (!String(args[0]).startsWith('/api/events/export.csv?')) return response;
        window.fetch = original;
        return new Promise(resolve => {
          window.releaseOldExport = () => resolve(new Response('id;tipo\\n1;teste', {
            headers: {'X-EverLock-Next-Cursor': '99', 'X-EverLock-Row-Count': '5000'}
          }));
          document.body.dataset.testPendingExport = 'true';
        });
      };
    }""")
    page.locator("#history-export").click()
    expect(page.locator("body")).to_have_attribute("data-test-pending-export", "true")
    page.locator('#history-filter [name="q"]').fill("novo filtro")
    expect(page.locator("#history-export")).to_be_enabled()
    page.evaluate("""async () => {
      window.releaseOldExport();
      await new Promise(requestAnimationFrame);
    }""")
    expect(page.locator("#history-export")).to_have_text("Baixar CSV")
    with page.expect_download(), page.expect_request("**/api/events/export.csv?*") as requested:
        page.locator("#history-export").click()
    query = parse_qs(urlsplit(requested.value.url).query)
    assert query["q"] == ["novo filtro"]
    assert "before_id" not in query


def test_consent_cancelled_during_response_never_starts_camera(page):
    # Canvas frames: never requests a physical device or produces personal images.
    page.add_init_script("""
      window.testCameraStarts = 0;
      navigator.mediaDevices.getUserMedia = async () => {
        window.testCameraStarts += 1;
        const canvas = document.createElement('canvas');
        canvas.width = 640; canvas.height = 480;
        const context = canvas.getContext('2d');
        window.setInterval(() => context.fillRect(0, 0, 640, 480), 50);
        return canvas.captureStream(10);
      };
    """)
    page.route("**/api/faces/status", lambda route: route.fulfill(json={
        "available": True, "model": "Motor sintético", "reason": "",
    }))
    login(page)
    expect(page.locator("#face-entry-title")).to_have_text("Reconhecimento facial por câmera")
    response = page.request.post("/api/identities", data={
        "label": "Pessoa sintética", "consent": True, "consent_version": CONSENT_VERSION,
    })
    assert response.status == 201
    identity = response.json()
    navigate(page, "identidades")
    policy = {
        "id": identity["id"], "version": CONSENT_VERSION, "text": "Termo de teste",
        "retention": 30, "expiresAt": identity["expires_at"],
    }
    start_panel = """policy => document.dispatchEvent(new CustomEvent(
      'everlock-face-enroll', {detail: policy}))"""
    page.evaluate(start_panel, policy)
    expect(page.locator("#face-enroll-prepare")).to_be_disabled()
    assert page.evaluate("window.testCameraStarts") == 0
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (!String(args[0]).endsWith('/consent/confirm')) return response;
        window.fetch = original;
        return new Promise(resolve => {
          window.releaseOldConsent = () => resolve(response);
          document.body.dataset.testPendingConsent = 'true';
        });
      };
    }""")
    page.locator("#face-subject-consent").check()
    page.locator("#face-enroll-prepare").click()
    expect(page.locator("body")).to_have_attribute("data-test-pending-consent", "true")
    page.locator("#face-subject-consent").uncheck()
    page.evaluate("""async () => {
      window.releaseOldConsent();
      await new Promise(requestAnimationFrame);
    }""")
    expect(page.locator("#face-enroll-panel")).to_be_hidden()
    assert page.evaluate("window.testCameraStarts") == 0
    page.evaluate(start_panel, policy)
    page.locator("#face-subject-consent").check()
    page.locator("#face-enroll-prepare").click()
    expect(page.locator("#face-enroll-start")).to_be_enabled()
    expect(page.locator("#face-enroll-prepare")).to_be_disabled()
    assert page.evaluate("window.testCameraStarts") == 1
    page.locator("#face-enroll-cancel").click()
    expect(page.locator("#face-enroll-video")).to_be_hidden()
