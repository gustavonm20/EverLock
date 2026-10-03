from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from everlock.app import create_app

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}


def sign_in(client):
    if client.get("/api/auth/session").json()["setup_required"]:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
    login = {"identifier": "admin", "password": ADMIN["password"]}
    assert client.post("/api/auth/login", json=login).status_code == 200


@pytest.fixture
def channel(tmp_path):
    mono, wall = [100.0], [1000.0]
    app = create_app(tmp_path / "network.sqlite3", clock=lambda: 0,
                     session_clock=lambda: wall[0], command_clock=lambda: mono[0])
    with TestClient(app, base_url="http://localhost") as client:
        sign_in(client)
        yield client, mono, wall, app


def network(client, internet=True, lan=True, delay=0):
    return client.post("/api/simulation/network", json={
        "internet_available": internet, "lan_available": lan, "delay_seconds": delay,
    })


def command(client, action="unlock", ttl=10):
    version = client.get("/api/status").json()["door"]["version"]
    return {"command_id": str(uuid4()), "action": action,
            "expected_version": version, "valid_for_seconds": ttl}


def result(client, payload):
    return client.get(f"/api/commands/{payload['command_id']}").json()


def test_request_accept_execute_and_duplicate_only_once(channel):
    client, _, _, _ = channel
    payload = command(client)
    response = client.post("/api/commands", json=payload)
    assert response.status_code == 202
    assert response.json()["command"]["status"] == "requested"
    completed = result(client, payload)
    assert completed["status"] == "executed"
    assert [t["status"] for t in completed["transitions"]] == [
        "requested", "accepted", "executed",
    ]
    duplicate = client.post("/api/commands", json=payload)
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
    assert duplicate.json()["command"] == completed
    events = client.get("/api/events?limit=100").json()["items"]
    unlocked = [e for e in events if e["type"] == "unlock"]
    assert len(unlocked) == 1 and unlocked[0]["actor"] == "admin"
    assert unlocked[0]["source"] == "remote"
    conflict = client.post("/api/commands", json={**payload, "action": "lock"})
    assert conflict.status_code == 409


def test_deadline_is_real_and_inclusive_not_virtual_or_wall_clock(channel):
    client, mono, wall, _ = channel
    network(client, delay=15)
    payload = command(client, ttl=10)
    client.post("/api/commands", json=payload)
    client.post("/api/simulation/clock", json={"paused": True})
    client.post("/api/simulation/clock", json={"advance_seconds": 86400})
    wall[0] -= 500  # Correção do relógio de calendário não prolonga o prazo monotônico.
    assert result(client, payload)["status"] == "requested"
    mono[0] += 10
    assert result(client, payload)["status"] == "expired"
    mono[0] += 20
    assert result(client, payload)["status"] == "expired"
    assert client.get("/api/status").json()["door"]["secured"]


@pytest.mark.parametrize("fault,reason", [
    ({"internet": False}, "internet_unavailable"),
    ({"lan": False}, "lan_unavailable"),
])
def test_network_loss_cancels_pending_and_preserves_local_access(channel, fault, reason):
    client, mono, _, _ = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    before = client.get("/api/communication").json()["observation"]
    state = network(client, **fault).json()
    assert state["observation_stale"] and state["observation"] == before
    assert result(client, payload)["code"] == reason
    assert client.post("/api/actions", json={"action": "unlock"}).status_code == 200
    assert client.post("/api/actions", json={"action": "open"}).status_code == 200
    mono[0] += 3
    stale = client.get("/api/communication").json()
    assert stale["observation"]["door"]["position"] == "closed"
    assert stale["observation_age_seconds"] >= 3
    connected = network(client).json()
    assert not connected["observation_stale"]
    assert connected["observation"]["door"]["position"] == "open"
    assert result(client, payload)["status"] == "failed"


def test_reject_offline_submission_and_remote_lock_does_not_close_door(channel):
    client, _, _, _ = channel
    network(client, internet=False)
    payload = command(client)
    assert client.post("/api/commands", json=payload).status_code == 409
    network(client)
    assert result(client, payload)["status"] == "failed"
    client.post("/api/actions", json={"action": "exit"})
    lock = command(client, "lock")
    client.post("/api/commands", json=lock)
    assert result(client, lock)["code"] == "door_open"
    assert client.get("/api/status").json()["door"]["position"] == "open"


def test_conflicting_commands_use_door_version_not_energy_revision(channel):
    client, mono, _, app = channel
    network(client, delay=2)
    unlock, lock = command(client), command(client, "lock")
    client.post("/api/commands", json=unlock)
    client.post("/api/commands", json=lock)
    client.post("/api/simulation/power", json={"mains_available": False})
    # O relógio falso não pode mudar entre as leituras de um tick em segundo plano.
    # Os dois comandos devem ficar prontos no mesmo instante deste cenário.
    with app.state.controller.mutex:
        mono[0] += 2
        app.state.communication.tick()
    assert result(client, unlock)["status"] == "executed"
    assert result(client, lock)["code"] == "state_conflict"
    fresh_lock = command(client, "lock")
    client.post("/api/commands", json=fresh_lock)
    with app.state.controller.mutex:
        mono[0] += 2
        app.state.communication.tick()
    assert result(client, fresh_lock)["status"] == "executed"
    assert client.get("/api/status").json()["door"]["secured"]
    assert client.post("/api/actions", json={"action": "exit"}).status_code == 200


def test_power_failure_cancels_command_and_keeps_manual_exit(channel):
    client, mono, _, _ = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    client.post("/api/simulation/power/config", json={"initial_percent": 5})
    client.post("/api/simulation/power", json={"mains_available": False})
    state = client.get("/api/communication").json()
    assert state["internet_available"] and state["lan_available"]
    assert not state["device_available"] and state["observation_stale"]
    assert result(client, payload)["code"] == "device_unavailable"
    assert client.post("/api/actions", json={"action": "exit"}).status_code == 200
    client.post("/api/simulation/power", json={"mains_available": True})
    client.post("/api/simulation/clock", json={"advance_seconds": 2})
    mono[0] += 3
    assert result(client, payload)["status"] == "failed"


def test_logout_invalidates_command_waiting_for_delivery(channel):
    client, mono, _, _ = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    client.post("/api/auth/logout", json={})
    mono[0] += 2
    sign_in(client)
    assert result(client, payload)["code"] == "authorization_revoked"
    assert client.get("/api/status").json()["door"]["secured"]


def test_permissions_visibility_and_revocation_at_execution(channel):
    client, mono, _, _ = channel
    network(client, delay=2)
    client.post("/api/auth/users", json={"username": "pessoa", "email": "pessoa@example.com",
                                         "password": ADMIN["password"]})
    admin_token = client.cookies.get("everlock_session")
    admin_command = command(client, "lock")
    client.post("/api/commands", json=admin_command)
    client.post("/api/auth/login", json={"identifier": "pessoa", "password": ADMIN["password"]})
    assert network(client).status_code == 403
    assert client.get(f"/api/commands/{admin_command['command_id']}").status_code == 404
    assert client.get("/api/communication").json()["commands"] == []
    user_command = command(client)
    client.post("/api/commands", json=user_command)
    client.cookies.clear()
    client.cookies.set("everlock_session", admin_token)
    client.patch("/api/auth/users/2", json={"role": "user", "active": False})
    mono[0] += 2
    assert result(client, user_command)["code"] == "authorization_revoked"
    assert client.get("/api/status").json()["door"]["secured"]


def test_restart_fails_pending_without_replay_and_preserves_history(tmp_path):
    path = tmp_path / "restart.sqlite3"
    for first in (True, False):
        with TestClient(create_app(path, clock=lambda: 0, command_clock=lambda: 0),
                        base_url="http://localhost") as client:
            sign_in(client)
            if first:
                network(client, delay=10)
                payload = command(client)
                client.post("/api/commands", json=payload)
            else:
                assert result(client, payload)["code"] == "restart_interrupted"
                retry = client.post("/api/commands", json=payload).json()
                assert retry["duplicate"] and retry["command"]["status"] == "failed"
                assert client.get("/api/status").json()["door"]["secured"]


def test_final_record_and_actuation_roll_back_together(channel, monkeypatch):
    client, mono, _, app = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    storage = app.state.controller.storage
    original = storage.finish_command

    def fail_after_record(command_id, status, code, message, now):
        original(command_id, status, code, message, now)
        if status == "executed":
            raise RuntimeError("Falha de gravação preparada para o teste")

    with app.state.controller.mutex:
        monkeypatch.setattr(storage, "finish_command", fail_after_record)
        mono[0] += 2
        with pytest.raises(RuntimeError):
            app.state.communication.tick()
    assert result(client, payload)["code"] == "execution_interrupted"
    assert client.get("/api/status").json()["door"]["secured"]
    assert not any(e["type"] == "unlock" for e in client.get("/api/events").json()["items"])


def test_command_validation_and_anonymous_access(channel):
    client, _, _, _ = channel
    payload = command(client)
    for change in ({"valid_for_seconds": True}, {"valid_for_seconds": 0},
                   {"valid_for_seconds": 31}, {"action": "exit"}, {"admin": True},
                   {"expected_version": "qualquer"}):
        assert client.post("/api/commands", json={**payload, **change}).status_code == 422
    assert network(client, delay="Infinity").status_code == 422
    assert network(client, internet="false").status_code == 422
    client.post("/api/auth/logout", json={})
    assert client.get("/api/communication").status_code == 401
    assert client.get(f"/api/commands/{payload['command_id']}").status_code == 401
    assert client.post("/api/commands", json=payload).status_code == 401
    assert network(client).status_code == 401


def test_power_cut_is_recorded_even_if_recovered_before_channel_poll(channel):
    client, mono, _, _ = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    client.post("/api/simulation/power/config", json={"initial_percent": 5})
    client.post("/api/simulation/power", json={"mains_available": False})
    client.post("/api/simulation/power", json={"mains_available": True})
    client.post("/api/simulation/clock", json={"advance_seconds": 2})
    mono[0] += 3
    assert result(client, payload)["code"] == "device_unavailable"
    assert client.get("/api/status").json()["door"]["secured"]


def test_submission_limit_exempts_duplicate_and_does_not_actuate(channel):
    client, _, _, _ = channel
    network(client, delay=30)
    payloads = [command(client) for _ in range(11)]
    for payload in payloads[:10]:
        assert client.post("/api/commands", json=payload).status_code == 202
    assert client.post("/api/commands", json=payloads[10]).status_code == 429
    duplicate = client.post("/api/commands", json=payloads[0])
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
    assert client.get("/api/status").json()["door"]["secured"]


def test_session_expiration_prevents_delayed_execution(channel):
    client, mono, wall, _ = channel
    network(client, delay=2)
    payload = command(client)
    client.post("/api/commands", json=payload)
    wall[0] += 86400
    mono[0] += 2
    sign_in(client)
    assert result(client, payload)["code"] == "authorization_revoked"
    assert client.get("/api/status").json()["door"]["secured"]
