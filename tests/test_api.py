import asyncio

import pytest
from fastapi.testclient import TestClient

from everlock.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.sqlite3"), base_url="http://localhost") as client:
        yield client


def test_health_status_and_assets(client):
    assert client.get("/api/health").json()["mode"] == "simulation"
    status = client.get("/api/status").json()
    assert status["door"]["secured"]
    assert status["capabilities"] == {
        "door": True, "power": True, "connectivity": False,
        "face_recognition": False, "authentication": False,
    }
    page = client.get("/")
    assert page.status_code == 200
    assert "EverLock" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    for asset in ("styles.css", "app.js"):
        assert client.get(f"/static/{asset}").status_code == 200


def test_action_results_history_and_revision(client):
    before = client.get("/api/status").json()["revision"]
    denied = client.post("/api/actions", json={"action": "open"})
    assert denied.status_code == 409
    assert denied.json()["code"] == "door_locked"
    assert denied.json()["state"]["door"]["secured"]
    unlocked = client.post("/api/actions", json={"action": "unlock"})
    assert unlocked.status_code == 200
    assert unlocked.json()["state"]["revision"] > before
    assert client.post("/api/actions", json={"action": "open"}).status_code == 200
    ended = client.post("/api/actions", json={"action": "end_release"}).json()
    assert ended["state"]["door"]["lock"] == "pending_close"
    closed = client.post("/api/actions", json={"action": "close"}).json()
    assert closed["state"]["door"]["secured"]
    events = client.get("/api/events?limit=100").json()["items"]
    assert events[0]["type"] == "close"
    assert any(event["outcome"] == "denied" for event in events)


@pytest.mark.parametrize("payload", [
    {"action": "delete"}, {}, {"action": "unlock", "admin": True},
])
def test_invalid_actions_do_not_mutate_state(client, payload):
    before = client.get("/api/status").json()["revision"]
    assert client.post("/api/actions", json=payload).status_code == 422
    assert client.get("/api/status").json()["revision"] == before


@pytest.mark.parametrize("headers", [
    {"Origin": "https://outro-site.example"},
    {"Origin": "http://localhost:9000"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_cross_origin_actions_are_rejected(client, headers):
    response = client.post("/api/actions", json={"action": "unlock"}, headers=headers)
    assert response.status_code == 403
    assert client.get("/api/status").json()["door"]["secured"]


def test_same_origin_is_allowed(client):
    response = client.post(
        "/api/actions", json={"action": "unlock"}, headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 200


def test_foreign_host_and_non_json_are_rejected(client):
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/actions", data={"action": "unlock"}).status_code == 415


@pytest.mark.parametrize("limit", [0, 101, "invalid"])
def test_event_limit_is_bounded(client, limit):
    assert client.get(f"/api/events?limit={limit}").status_code == 422


def test_background_task_expires_release_without_another_request(tmp_path):
    clock = [100.0]
    app = create_app(tmp_path / "timer.sqlite3", clock=lambda: clock[0])
    with TestClient(app, base_url="http://localhost") as client:
        client.post("/api/actions", json={"action": "unlock"})
        clock[0] = 103.0
        client.portal.call(asyncio.sleep, 0.25)
        assert app.state.controller.door.secured


def test_power_scenario_through_api(tmp_path):
    with TestClient(create_app(tmp_path / "power.sqlite3", clock=lambda: 0),
                    base_url="http://localhost") as client:
        assert client.post("/api/simulation/power/config", json={}).status_code == 200
        cut = client.post("/api/simulation/power", json={"mains_available": False})
        assert cut.status_code == 200
        result = client.post("/api/simulation/clock", json={"advance_seconds": 86400})
        assert result.status_code == 200
        state = result.json()["state"]
        assert state["device"]["status"] == "powered_off"
        assert state["power"]["battery"]["stored_wh"] == 0
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.post("/api/actions", json={"action": "unlock"}).status_code == 409
        assert client.post("/api/actions", json={"action": "exit"}).status_code == 200
        result = client.post("/api/simulation/power", json={"mains_available": True}).json()
        assert result["state"]["device"]["status"] == "recovering"
        assert result["state"]["door"]["lock"] == "pending_close"
        assert result["state"]["door"]["release_remaining_seconds"] == 0
        result = client.post("/api/simulation/clock", json={"advance_seconds": 2}).json()
        assert result["state"]["device"]["status"] == "online"
        assert result["state"]["door"]["release_remaining_seconds"] == 0


@pytest.mark.parametrize("path, payload", [
    ("clock", {}), ("clock", {"speed": 100000}), ("clock", {"speed": True}),
    ("clock", {"paused": "yes"}), ("clock", {"advance_seconds": -1}),
    ("clock", {"advance_seconds": 86401}), ("clock", {"speed": 60, "paused": True}),
    ("clock", {"advance_seconds": "Infinity"}),
    ("power", {"mains_available": "false"}),
    ("power/config", {"capacity_wh": 0}),
    ("power/config", {"economy_load_w": 90}),
    ("power/config", {"initial_percent": 101}),
    ("power/config", {"efficiency": "NaN"}),
])
def test_invalid_simulation_payloads_are_rejected(client, path, payload):
    before = client.get("/api/status").json()
    assert client.post(f"/api/simulation/{path}", json=payload).status_code == 422
    after = client.get("/api/status").json()
    assert after["revision"] == before["revision"]
    assert after["power"] == before["power"]


def test_power_configuration_rejects_cross_origin_requests(client):
    result = client.post("/api/simulation/power/config", json={},
                         headers={"Origin": "https://outside.example"})
    assert result.status_code == 403
