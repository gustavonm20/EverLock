"""Camera readiness and late permission results with synthetic canvas streams."""

import pytest
from playwright.sync_api import expect
from test_diagnostics import login
from test_navigation_history_consent import navigate

from everlock.identities import CONSENT_VERSION


def enrollment_panel(page):
    page.route("**/api/faces/status", lambda route: route.fulfill(json={
        "available": True, "model": "Motor sintético", "reason": "",
    }))
    login(page)
    expect(page.locator("#face-entry-title")).to_have_text("Reconhecimento facial por câmera")
    response = page.request.post("/api/identities", data={
        "label": "Ensaio sintético", "consent": True, "consent_version": CONSENT_VERSION,
    })
    assert response.status == 201
    identity = response.json()
    navigate(page, "identidades")
    policy = {"id": identity["id"], "version": CONSENT_VERSION, "text": "Termo de teste",
              "retention": 30, "expiresAt": identity["expires_at"]}
    page.evaluate("""policy => {
      window.testPolicy = policy;
      document.dispatchEvent(new CustomEvent('everlock-face-enroll', {detail: policy}));
    }""", policy)
    page.locator("#face-subject-consent").check()
    page.locator("#face-enroll-prepare").click()


@pytest.mark.parametrize("departure", ["cancel", "logout"])
def test_late_camera_permission_stops_old_stream_and_allows_retry(page, departure):
    page.add_init_script("""
      window.testCameraStarts = 0;
      window.makeCanvasStream = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 640; canvas.height = 480;
        const ctx = canvas.getContext('2d');
        setInterval(() => ctx.fillRect(0, 0, 640, 480), 50);
        return canvas.captureStream(10);
      };
      navigator.mediaDevices.getUserMedia = () => {
        window.testCameraStarts += 1;
        if (window.testCameraStarts === 1) return new Promise(resolve => {
          window.resolveLateCamera = resolve;
          document.body.dataset.cameraPermissionPending = 'true';
        });
        window.currentCamera = window.makeCanvasStream();
        return Promise.resolve(window.currentCamera);
      };
    """)
    enrollment_panel(page)
    expect(page.locator("body")).to_have_attribute("data-camera-permission-pending", "true")
    expect(page.locator("#face-enroll-start")).to_be_disabled()
    if departure == "logout":
        page.locator("#logout").click()
        expect(page.locator("#auth-panel")).to_be_visible()
    else:
        page.locator("#face-enroll-cancel").click()
        expect(page.locator("#face-enroll-panel")).to_be_hidden()
        page.evaluate("""() => document.dispatchEvent(new CustomEvent(
          'everlock-face-enroll', {detail: window.testPolicy}))""")
        page.locator("#face-subject-consent").check()
        page.locator("#face-enroll-prepare").click()
        expect(page.locator("#face-enroll-start")).to_be_enabled()
        assert page.evaluate("window.testCameraStarts") == 2
    assert page.evaluate("""async () => {
      window.lateCamera = window.makeCanvasStream();
      window.resolveLateCamera(window.lateCamera);
      await Promise.resolve();
      return window.lateCamera.getTracks().every(t => t.readyState === 'ended');
    }""")
    if departure == "cancel":
        assert page.evaluate("""() => document.getElementById('face-enroll-video').srcObject
          === window.currentCamera
          && window.currentCamera.getVideoTracks()[0].readyState === 'live'""")
        page.locator("#face-enroll-cancel").click()
    expect(page.locator("#face-enroll-video")).to_be_hidden()


def test_camera_without_frames_never_enables_capture(page):
    page.add_init_script("""
      navigator.mediaDevices.getUserMedia = async () => {
        document.body.dataset.cameraOpenedWithoutFrames = 'true';
        return new MediaStream();
      };
      HTMLMediaElement.prototype.play = async () => {};
    """)
    enrollment_panel(page)
    expect(page.locator("body")).to_have_attribute("data-camera-opened-without-frames", "true")
    expect(page.locator("#face-enroll-start")).to_be_disabled()
    assert page.evaluate("""() => {
      try { window.FaceKit.capture(document.getElementById('face-enroll-video')); }
      catch (error) { return error.message; }
      return '';
    }""") == "A câmera ainda não tem uma imagem disponível. Confira a prévia e tente novamente."
    page.locator("#face-enroll-cancel").click()
    expect(page.locator("#face-enroll-panel")).to_be_hidden()
