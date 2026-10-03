"""Cenários completos pela API, com motor facial falso e banco temporário.

As capturas são textos sintéticos lidos por FakeFaceEngine. Estes testes comprovam
as regras do simulador; não medem precisão facial ou resistência a ataques reais.
"""

import base64
from uuid import uuid4

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.identities import CONSENT_VERSION

EPOCH = 1_790_000_000.0
ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}


def scenario_app(path, real):
    return create_app(path, clock=lambda: 0, session_clock=lambda: EPOCH,
                      command_clock=lambda: real[0], face_engine=FakeFaceEngine())


def sign_in(client):
    if client.get("/api/auth/session").json()["setup_required"]:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
    login = {"identifier": "admin", "password": ADMIN["password"]}
    assert client.post("/api/auth/login", json=login).status_code == 200


def synthetic_capture(person, number, yaw=0.0):
    return base64.b64encode(f"PESSOA:{person}:{number}:{yaw}".encode()).decode()


def enroll(client, person):
    created = client.post("/api/identities", json={
        "label": person, "consent": True, "consent_version": CONSENT_VERSION,
    })
    assert created.status_code == 201, created.text
    identity = created.json()
    registered = client.post(f"/api/identities/{identity['id']}/face", json={
        "images": [synthetic_capture(person, number) for number in range(3)],
    })
    assert registered.status_code == 201, registered.text
    return identity["id"]


def capture_challenge(client, person):
    response = client.post("/api/recognition/challenge", json={})
    assert response.status_code == 200, response.text
    challenge = response.json()
    yaw = 0.30 if challenge["direction"] == "left" else -0.30
    return {
        "challenge_id": challenge["challenge_id"],
        "front": synthetic_capture(person, "frente-de-teste"),
        "turned": [synthetic_capture(person, f"giro-de-teste-{n}", yaw) for n in range(3)],
    }


def recognize(client, person):
    return client.post("/api/recognition/verify", json=capture_challenge(client, person))


def advance(client, seconds):
    response = client.post("/api/simulation/clock", json={"advance_seconds": seconds})
    assert response.status_code == 200, response.text
    return response.json()["state"]


def door(client):
    return client.get("/api/status").json()["door"]


def facial_releases(client):
    events = client.get("/api/events?type=unlock&source=recognition&limit=100")
    assert events.status_code == 200
    return events.json()["items"]


@pytest.fixture
def scenario(tmp_path):
    real = [100.0]
    with TestClient(scenario_app(tmp_path / "integrated.sqlite3", real),
                    base_url="http://localhost") as client:
        sign_in(client)
        assert client.post("/api/simulation/clock", json={"paused": True}).status_code == 200
        assert client.get("/api/faces/status").json()["model"] == "falso"
        yield client


def test_consented_face_release_energy_failure_manual_access_and_recovery(scenario):
    client = scenario
    identity_id = enroll(client, "Pessoa Energia")

    recognized = recognize(client, "Pessoa Energia")
    assert recognized.status_code == 200, recognized.text
    assert recognized.json()["identity_id"] == identity_id
    released = recognized.json()["state"]["door"]
    assert released["position"] == "closed" and released["lock"] == "released"
    assert released["release_remaining_seconds"] == 3
    assert advance(client, 2)["door"]["release_remaining_seconds"] == 1
    expired = advance(client, 1)["door"]
    assert expired["secured"] and expired["position"] == "closed"

    assert client.post("/api/simulation/power/config",
                       json={"initial_percent": 5}).status_code == 200
    cut = client.post("/api/simulation/power", json={"mains_available": False})
    assert cut.status_code == 200 and cut.json()["state"]["device"]["status"] == "powered_off"
    unavailable = recognize(client, "Pessoa Energia")
    assert unavailable.status_code == 409
    assert unavailable.json()["code"] == "device_powered_off" and door(client)["secured"]

    for action in ("exit", "close", "key_entry", "close"):
        response = client.post("/api/actions", json={"action": action})
        assert response.status_code == 200, response.text
        expected_position = "open" if action in {"exit", "key_entry"} else "closed"
        assert response.json()["state"]["door"]["position"] == expected_position
    assert door(client)["secured"]

    restored = client.post("/api/simulation/power", json={"mains_available": True})
    assert restored.status_code == 200
    assert restored.json()["state"]["device"]["status"] == "recovering"
    recovered = advance(client, 2)
    assert recovered["device"]["status"] == "online"
    assert recovered["door"]["secured"] and recovered["door"]["release_remaining_seconds"] == 0
    assert len(facial_releases(client)) == 1


def test_identity_removal_after_challenge_prevents_a_new_facial_release(scenario):
    client = scenario
    revoked_id = enroll(client, "Pessoa Revogada")
    deleted_id = enroll(client, "Pessoa Excluida")

    for identity_id, person, removal, expected_code in (
        (revoked_id, "Pessoa Revogada", "revoke", "no_match"),
        (deleted_id, "Pessoa Excluida", "delete", "no_faces_enrolled"),
    ):
        assert recognize(client, person).status_code == 200
        assert advance(client, 3)["door"]["secured"]
        pending_capture = capture_challenge(client, person)
        target = f"/api/identities/{identity_id}"
        removed = (client.post(f"{target}/consent/revoke", json={}) if removal == "revoke"
                   else client.delete(target, headers={"Content-Type": "application/json"}))
        assert removed.status_code == 200, removed.text
        before = door(client)
        denied = client.post("/api/recognition/verify", json=pending_capture)
        assert denied.status_code == 409 and denied.json()["code"] == expected_code
        after = door(client)
        assert after["secured"] and after["version"] == before["version"]

    identities = client.get("/api/identities").json()["items"]
    assert len(identities) == 1 and identities[0]["id"] == revoked_id
    assert identities[0]["state"] == "revoked" and identities[0]["face_samples"] == 0
    audit = client.get("/api/identities/events").json()["items"]
    assert {"consent_revoked", "identity_deleted"} <= {item["type"] for item in audit}
    assert len(facial_releases(client)) == 2


def test_restart_preserves_consent_but_replays_neither_face_release_nor_remote_command(tmp_path):
    path, real = tmp_path / "restart.sqlite3", [100.0]
    with TestClient(scenario_app(path, real), base_url="http://localhost") as client:
        sign_in(client)
        assert client.post("/api/simulation/clock", json={"paused": True}).status_code == 200
        identity_id = enroll(client, "Pessoa Reinicio")
        network = {"internet_available": True, "lan_available": True, "delay_seconds": 30}
        assert client.post("/api/simulation/network", json=network).status_code == 200
        command = {"command_id": str(uuid4()), "action": "unlock",
                   "expected_version": door(client)["version"], "valid_for_seconds": 30}
        assert client.post("/api/commands", json=command).status_code == 202
        assert recognize(client, "Pessoa Reinicio").status_code == 200
        old_capture = capture_challenge(client, "Pessoa Reinicio")
        assert door(client)["lock"] == "released"

    with TestClient(scenario_app(path, real), base_url="http://localhost") as client:
        sign_in(client)
        restarted = client.get("/api/status").json()
        assert restarted["door"]["secured"]
        assert restarted["simulation"]["paused"] and restarted["simulation"]["speed"] == 1
        assert restarted["door"]["release_remaining_seconds"] == 0
        identities = client.get("/api/identities").json()["items"]
        assert len(identities) == 1 and identities[0]["id"] == identity_id
        assert identities[0]["state"] == "ready" and identities[0]["face_samples"] == 3

        old_attempt = client.post("/api/recognition/verify", json=old_capture)
        assert old_attempt.status_code == 409 and old_attempt.json()["code"] == "challenge_expired"
        command_path = f"/api/commands/{command['command_id']}"
        interrupted = client.get(command_path).json()
        assert interrupted["status"] == "failed" and interrupted["code"] == "restart_interrupted"
        duplicate = client.post("/api/commands", json=command)
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
        real[0] += 31
        assert client.get(command_path).json()["status"] == "failed"
        assert door(client)["secured"] and len(facial_releases(client)) == 1
        remote_releases = client.get("/api/events?type=unlock&source=remote").json()["items"]
        assert remote_releases == []

        assert recognize(client, "Pessoa Reinicio").status_code == 200
        assert advance(client, 3)["door"]["secured"]
        assert len(facial_releases(client)) == 2
