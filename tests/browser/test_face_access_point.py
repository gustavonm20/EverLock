"""Jornada de navegador: cadastro do próprio rosto -> ponto de acesso -> trava virtual.

Sem pessoas, fotos humanas ou câmera física. A câmera é um canvas gerado pelo teste e cada
captura vira um texto sintético que o FakeFaceEngine (dublê de teste explícito) entende. O
servidor, as regras de autorização, a trava virtual e a interface são os reais. Isso comprova a
integração da tela com o servidor; não mede precisão facial nem prova de vida.
"""

import sys
from pathlib import Path

import httpx
import pytest
from conftest import PASSWORD
from playwright.sync_api import expect
from test_diagnostics import login
from test_navigation_history_consent import navigate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fakes import FakeFaceEngine  # noqa: E402

from everlock.identities import CONSENT_VERSION  # noqa: E402


@pytest.fixture
def face_engine():
    return FakeFaceEngine()


def synthetic_camera(page):
    """Câmera de canvas e capturas sintéticas: "enroll" (5 fotos) ou "verify" (frente + giro)."""
    page.add_init_script("""
      window.testPerson = 'visitante';
      let enrollShot = 0, verifyShot = 0;
      let kit;
      Object.defineProperty(window, 'FaceKit', {
        get: () => kit,
        set: original => {
          kit = {...original,
            pause: () => Promise.resolve(),
            capture: video => {
              original.capture(video);  // exige a prévia viva, como na câmera real
              // Cada reconhecimento faz exatamente 7 capturas: 1 de frente e 6 do giro.
              const box = document.querySelector('#access-decision');
              const verifying = box?.dataset.outcome === 'working';
              let text;
              if (!verifying) text = `PESSOA:${window.testPerson}:${enrollShot++}`;
              else {
                const shot = verifyShot++;
                text = shot % 7 === 0 ? `PESSOA:${window.testPerson}:frente${shot}:0.0`
                  : `PESSOA:${window.testPerson}:giro${shot}:${shot % 2 ? 0.3 : -0.3}`;
              }
              return btoa(text);
            }
          };
        }
      });
      navigator.mediaDevices.getUserMedia = async () => {
        const canvas = document.createElement('canvas');
        canvas.width = 640; canvas.height = 480;
        const context = canvas.getContext('2d');
        setInterval(() => { context.fillStyle = '#345'; context.fillRect(0, 0, 640, 480); }, 50);
        return canvas.captureStream(10);
      };
    """)


def link_identity_to_visitor(local_server):
    with httpx.Client(base_url=local_server.url, trust_env=False) as client:
        assert client.post("/api/auth/login", json={
            "identifier": "admin", "password": PASSWORD}).status_code == 200
        users = client.get("/api/auth/users").json()["items"]
        visitor = next(user["id"] for user in users if user["username"] == "visitante")
        created = client.post("/api/identities", json={
            "label": "Visitante 01", "consent": True, "consent_version": CONSENT_VERSION,
            "account_id": visitor})
        assert created.status_code == 201, created.text
        return created.json()["id"]


def logout(page):
    page.locator("#logout").click()
    expect(page.locator("#auth-panel")).to_be_visible()


def self_enroll(page):
    login(page, "visitante")
    navigate(page, "contas")
    expect(page.locator("#door-access-facts")).to_contain_text("Visitante 01")
    page.locator("#door-access-consent").check()
    page.locator("#door-access-prepare").click()
    expect(page.locator("#door-access-start")).to_be_enabled()
    page.locator("#door-access-password").fill(PASSWORD)
    page.locator("#door-access-start").click()
    expect(page.locator("#door-access-step")).to_contain_text("Cadastro facial registrado")
    expect(page.locator("#door-access-facts")).to_contain_text("5 amostras")
    expect(page.locator("#door-access-facts")).to_contain_text("registrado por você")
    expect(page.locator("#door-access-video")).to_be_hidden()  # câmera desligada ao concluir
    logout(page)


def recognize(page):
    page.locator("#face-verify").focus()
    page.locator("#face-verify").click()


def test_self_enrolled_person_is_released_then_relocked(page, local_server):
    identity_id = link_identity_to_visitor(local_server)
    synthetic_camera(page)
    self_enroll(page)

    login(page)
    expect(page.locator("#access-engine")).to_have_attribute("data-kind", "test")
    page.locator("#face-camera-toggle").click()
    expect(page.locator("#face-verify")).to_be_enabled()
    recognize(page)
    decision = page.locator("#access-decision")
    expect(decision).to_have_attribute("data-outcome", "granted")
    expect(page.locator("#access-decision-title")).to_have_text(
        f"Acesso liberado · identidade #{identity_id}")
    expect(page.locator("#access-lock-state")).to_have_attribute("data-lock", "released")
    expect(page.locator("#release-meter")).to_be_visible()
    expect(page.locator("#lock-position")).to_have_text("Liberada")
    # Três segundos virtuais depois (relógio em 1x), a trava volta a engatar sozinha.
    expect(page.locator("#lock-position")).to_have_text("Engatada", timeout=8000)
    expect(decision).to_have_attribute("data-outcome", "relocked", timeout=8000)
    expect(page.locator("#release-meter")).to_be_hidden()
    expect(page.locator("#access-recent li").first).to_contain_text("Liberado")


def test_unknown_face_is_denied_and_manual_lock_stays_available(page, local_server):
    link_identity_to_visitor(local_server)
    synthetic_camera(page)
    self_enroll(page)

    login(page)
    page.evaluate("window.testPerson = 'desconhecido'")
    page.locator("#face-camera-toggle").click()
    expect(page.locator("#face-verify")).to_be_enabled()
    recognize(page)
    expect(page.locator("#access-decision")).to_have_attribute("data-outcome", "denied")
    expect(page.locator("#access-decision-title")).to_have_text("Rosto não reconhecido")
    expect(page.locator("#face-verify-result")).to_contain_text("trava permanece engatada")
    expect(page.locator("#lock-position")).to_have_text("Engatada")
    expect(page.locator("#access-recent li").first).to_contain_text("Negado")

    # Reconhecido e liberado; "Travar agora" engata na hora, sem esperar o prazo. O relógio
    # virtual fica pausado para que uma máquina lenta não deixe o prazo vencer antes do clique.
    # Usa a própria sessão do navegador: cada conta tem uma sessão por vez.
    assert page.evaluate("""() => fetch('/api/simulation/clock', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({paused: true})})
      .then(response => response.status)""") == 200
    page.evaluate("window.testPerson = 'visitante'")
    recognize(page)
    expect(page.locator("#access-decision")).to_have_attribute("data-outcome", "granted")
    lock_now = page.locator(".access-lock-now")
    expect(lock_now).to_be_enabled()
    lock_now.click()
    expect(page.locator("#lock-position")).to_have_text("Engatada")
    expect(lock_now).to_be_disabled()


def test_regular_user_sees_no_access_point_and_mobile_layout_fits(page, local_server):
    link_identity_to_visitor(local_server)
    login(page, "visitante")
    expect(page.locator("#access-point")).to_be_hidden()
    expect(page.locator(".access-user-note")).to_be_visible()
    for width, height in ((390, 844), (1440, 1000)):
        page.set_viewport_size({"width": width, "height": height})
        for section in ("simulador", "contas"):
            navigate(page, section)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), \
                f"Rolagem horizontal em {section}, largura {width}"
    expect(page.locator("#door-access-status")).to_contain_text("Leia o termo")
