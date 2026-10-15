"""Approved motion and capture indicators, with generated frames and gated pauses."""

import pytest
from conftest import PASSWORD
from playwright.sync_api import expect
from test_camera_lifecycle import enrollment_panel
from test_diagnostics import login
from test_navigation_history_consent import navigate


def controlled_camera(page):
    page.add_init_script("""
      window.testWaits = 0;
      window.testCaptures = 0;
      let kit;
      Object.defineProperty(window, 'FaceKit', {
        get: () => kit,
        set: original => {
          kit = {...original,
            pause: () => new Promise(resolve => {
              window.releaseCaptureWait = resolve;
              document.body.dataset.captureWait = String(++window.testWaits);
            }),
            capture: video => {
              const image = original.capture(video);
              window.testCaptures += 1;
              return image;
            }
          };
        }
      });
      navigator.mediaDevices.getUserMedia = async () => {
        const canvas = document.createElement('canvas');
        canvas.width = 640; canvas.height = 480;
        const context = canvas.getContext('2d');
        setInterval(() => context.fillRect(0, 0, 640, 480), 50);
        return canvas.captureStream(10);
      };
    """)


def release_pause(page, number):
    expect(page.locator("body")).to_have_attribute("data-capture-wait", str(number))
    page.evaluate("window.releaseCaptureWait()")


@pytest.mark.parametrize("kind", ["identity", "account"])
def test_capture_progress_counts_photos_not_approval_and_ignores_logout(page, tmp_path, kind):
    controlled_camera(page)
    submitted = []
    rejection = "Capturas recusadas no ensaio sintético."

    def reject_enrollment(route):
        submitted.append(route.request.post_data_json)
        route.fulfill(status=422, json={"message": rejection})

    if kind == "identity":
        page.route("**/api/identities/*/face", reject_enrollment)
        enrollment_panel(page)
        prefix, button, pauses = "face-enroll", "#face-enroll-start", 3
        expect(page.locator(button)).to_be_enabled()
        page.locator(button).click()
    else:
        page.route("**/api/auth/face/me", lambda route: route.fulfill(json={
            "available": True, "enrolled": False, "consent": {"text": "Termo sintético"},
        }))
        page.route("**/api/auth/face/enroll", reject_enrollment)
        login(page)
        navigate(page, "contas")
        page.locator('#account-face-form [name="password"]').fill(PASSWORD)
        page.locator('#account-face-form [name="consent"]').check()
        prefix, button, pauses = "account-face", "#account-face-submit", 1
        expect(page.locator(button)).to_be_enabled()
        page.locator(button).click()

    progress = page.locator(f"#{prefix}-progress")
    count = progress.locator("[data-capture-count]")
    expect(progress).to_be_visible()
    expect(count).to_have_text("0 de 5")
    assert page.evaluate("window.testCaptures") == 0
    for shot in range(5):
        expect(progress.locator('li[aria-current="step"]')).to_have_attribute(
            "aria-label", f"Foto {shot + 1}: em preparação",
        )
        for pause in range(pauses):
            release_pause(page, shot * pauses + pause + 1)
        expect(count).to_have_text(f"{shot + 1} de 5")
        expect(progress.locator('li[data-state="done"]')).to_have_count(shot + 1)
        assert page.evaluate("window.testCaptures") == shot + 1
        if shot == 0:
            for width, theme in ((1440, "light"), (390, "dark")):
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"{kind}-capturas-{width}.png"),
                                full_page=True)

    expect(page.locator(f"#{prefix}-step")).to_have_text(rejection)
    expect(page.locator(f"#{prefix}-step")).to_have_attribute("data-outcome", "error")
    expect(progress.locator("li[aria-current]")).to_have_count(0)
    expect(progress).to_contain_text("A aprovação depende da análise.")
    assert len(submitted) == 1 and len(submitted[0]["images"]) == 5

    # A new attempt resets the markers; resolving its paused work after logout
    # cannot repaint the indicator, take another photo or submit another batch.
    expect(page.locator(button)).to_be_enabled()
    page.locator(button).click()
    expect(count).to_have_text("0 de 5")
    expect(page.locator("body")).to_have_attribute("data-capture-wait", str(5 * pauses + 1))
    page.locator("#logout").click()
    expect(page.locator("#auth-panel")).to_be_visible()
    page.evaluate("""async () => {
      window.releaseCaptureWait();
      await Promise.resolve();
    }""")
    expect(progress).to_be_hidden()
    expect(count).to_have_text("0 de 5")
    expect(progress.locator('li[data-state="done"]')).to_have_count(0)
    assert page.evaluate("window.testCaptures") == 5
    assert len(submitted) == 1


def test_failed_capture_does_not_advance_the_indicator(page):
    controlled_camera(page)
    enrollment_panel(page)
    expect(page.locator("#face-enroll-start")).to_be_enabled()
    page.locator("#face-enroll-start").click()
    for number in range(1, 4):
        release_pause(page, number)
    progress = page.locator("#face-enroll-progress")
    expect(progress.locator("[data-capture-count]")).to_have_text("1 de 5")
    page.evaluate("window.FaceKit.stop(document.getElementById('face-enroll-video'))")
    for number in range(4, 7):
        release_pause(page, number)
    expect(page.locator("#face-enroll-step")).to_have_attribute("data-outcome", "error")
    expect(progress.locator("[data-capture-count]")).to_have_text("1 de 5")
    expect(progress.locator('li[data-state="done"]')).to_have_count(1)
    expect(progress.locator("li[aria-current]")).to_have_count(0)
    page.locator("#face-enroll-cancel").click()
    expect(progress).to_be_hidden()


@pytest.mark.parametrize("reduced", [False, True])
def test_motion_obeys_system_preference_without_changing_navigation(page, reduced):
    page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    login(page)
    navigate(page, "identidades")
    expect(page.locator("#identidades h2").first).to_be_focused()
    styles = page.locator("#identidades").evaluate("""element => ({
      animation: getComputedStyle(element).animationName,
      duration: getComputedStyle(element).animationDuration,
      progress: getComputedStyle(
        document.querySelector('#face-enroll-progress li')).transitionDuration
    })""")
    assert styles["animation"] == ("none" if reduced else "page-enter")
    assert styles["duration"] == ("0s" if reduced else "0.15s")
    assert (styles["progress"] == "0s") is reduced
    button = page.locator("#identity-submit")
    button.hover()
    transform = button.evaluate("""async element => {
      await Promise.all(element.getAnimations().map(a => a.finished.catch(() => {})));
      return getComputedStyle(element).transform;
    }""")
    assert (transform == "none") is reduced
    navigate(page, "diagnostico")
    expect(page.locator("#identidades")).to_be_hidden()
    expect(page.locator("#diagnostics-title")).to_be_focused()
