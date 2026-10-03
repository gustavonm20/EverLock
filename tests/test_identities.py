import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.identities import (
    CONSENT_VERSION,
    evaluate,
    format_time,
    parse_time,
    validate_label,
    validate_schedule,
    within_schedule,
)

EPOCH = 1_790_000_000.0  # setembro de 2026
ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
USER = {"username": "maria", "email": "maria@example.com", "password": "Outra senha 2!"}
JSON = {"Content-Type": "application/json"}


def today() -> int:
    return datetime.fromtimestamp(EPOCH).weekday()


def payload(label="Aluno 01", **extra):
    return {"label": label, "consent": True, "consent_version": CONSENT_VERSION, **extra}


def login(client, account=ADMIN):
    credentials = {"identifier": account["username"], "password": account["password"]}
    assert client.post("/api/auth/login", json=credentials).status_code == 200


@pytest.fixture
def lab(tmp_path):
    wall = [EPOCH]
    app = create_app(tmp_path / "identities.sqlite3", clock=lambda: 0,
                     session_clock=lambda: wall[0])
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        login(client)
        yield client, wall, app


def create(client, label="Aluno 01", **extra):
    response = client.post("/api/identities", json=payload(label, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def ready(client, label="Aluno 01", **extra):
    identity = create(client, label, **extra)
    enrolled = client.post(f"/api/identities/{identity['id']}/enrollment", headers=JSON)
    assert enrolled.status_code == 201
    return identity


def match(client, identity_id):
    return client.post("/api/recognition/simulate",
                       json={"scenario": "match", "identity_id": identity_id})


def door(client):
    return client.get("/api/status").json()["door"]


def event_types(client):
    return [event["type"] for event in client.get("/api/events?limit=100").json()["items"]]


# --- Regras puras -----------------------------------------------------------------------


@pytest.mark.parametrize(("days", "start", "end", "moment", "expected"), [
    ("01234", 480, 1080, datetime(2026, 9, 28, 9, 0), True),     # segunda 09:00
    ("01234", 480, 1080, datetime(2026, 9, 28, 8, 0), True),     # início é inclusivo
    ("01234", 480, 1080, datetime(2026, 9, 28, 18, 0), False),   # fim é exclusivo
    ("01234", 480, 1080, datetime(2026, 9, 28, 7, 59), False),
    ("01234", 480, 1080, datetime(2026, 10, 3, 9, 0), False),    # sábado
    ("4", 1320, 360, datetime(2026, 10, 2, 23, 0), True),        # sexta 23:00, atravessa
    ("4", 1320, 360, datetime(2026, 10, 3, 5, 59), True),        # sábado pertence à sexta
    ("4", 1320, 360, datetime(2026, 10, 3, 6, 0), False),
    ("4", 1320, 360, datetime(2026, 10, 2, 5, 0), False),        # sexta cedo pertence à quinta
    ("4", 1320, 360, datetime(2026, 10, 3, 23, 0), False),
    ("0123456", 0, 1440, datetime(2026, 10, 3, 23, 59), True),   # 24 horas
    ("0123456", 0, 1440, datetime(2026, 10, 3, 0, 0), True),
])
def test_schedule_window_rules(days, start, end, moment, expected):
    assert within_schedule(days, start, end, moment) is expected


def test_time_and_schedule_validation():
    assert parse_time("00:00", end=False) == 0
    assert parse_time("23:59", end=True) == 1439
    assert parse_time("24:00", end=True) == 1440
    assert format_time(1440) == "24:00" and format_time(75) == "01:15"
    for bad in ("8:00", "25:00", "12:60", "24:00 ", "24:30", "", "meio-dia"):
        with pytest.raises(ValueError):
            parse_time(bad, end=True)
    with pytest.raises(ValueError):
        parse_time("24:00", end=False)
    assert validate_schedule([4, 0, 0, 2], "08:00", "18:00") == ("024", 480, 1080)
    for days, start, end in (([], "08:00", "18:00"), ([7], "08:00", "18:00"),
                             ([-1], "08:00", "18:00"), ([True], "08:00", "18:00"),
                             ([1], "08:00", "08:00"), ([1], "00:00", "00:00")):
        with pytest.raises(ValueError):
            validate_schedule(days, start, end)


def test_label_policy():
    assert validate_label("  Aluno   01 ") == "Aluno 01"
    assert validate_label("José D'Ávila-2") == "José D'Ávila-2"
    assert validate_label("linha\nnova\t01") == "linha nova 01"  # espaços são normalizados
    for bad in ("a", "@@", "--", "x" * 41, "nome <script>", "a;b"):
        with pytest.raises(ValueError):
            validate_label(bad)


def test_decision_order_and_reasons():
    base = {
        "consent_revoked_at": None, "consent_granted_at": EPOCH, "retention_days": 30,
        "active": 1, "enrollment": "simulated", "face_samples": 0, "days": "0123456",
        "window_start": 0, "window_end": 1440,
    }
    assert evaluate(base, EPOCH).code == "authorized"
    other_day = str((today() + 1) % 7)
    assert evaluate({**base, "days": other_day}, EPOCH).code == "outside_schedule"
    assert evaluate({**base, "enrollment": "none"}, EPOCH).code == "not_enrolled"
    assert evaluate({**base, "active": 0}, EPOCH).code == "identity_inactive"
    assert evaluate(base, EPOCH + 30 * 86400).code == "retention_expired"
    assert evaluate({**base, "consent_revoked_at": EPOCH}, EPOCH).code == "consent_revoked"
    # A revogação vence qualquer outro motivo; o vencimento vence desativação e horário.
    worst = {**base, "consent_revoked_at": EPOCH, "active": 0, "enrollment": "none"}
    assert evaluate(worst, EPOCH + 90 * 86400).code == "consent_revoked"
    expired = {**base, "active": 0, "enrollment": "none"}
    assert evaluate(expired, EPOCH + 90 * 86400).code == "retention_expired"


# --- Permissões e validação -------------------------------------------------------------


def test_identities_require_an_administrator(lab):
    client, _, app = lab
    identity = ready(client)
    assert client.post("/api/auth/users", json={**USER, "role": "user"}).status_code == 201
    # Sem `with`: o ciclo de vida do app já está ativo pelo primeiro cliente.
    ordinary = TestClient(app, base_url="http://localhost")
    anonymous = [
        ordinary.get("/api/identities"), ordinary.get("/api/identities/policy"),
        ordinary.get("/api/identities/events"),
        ordinary.post("/api/identities", json=payload("Outro")),
        ordinary.post("/api/recognition/simulate", json={"scenario": "no_match"}),
    ]
    assert {response.status_code for response in anonymous} == {401}
    login(ordinary, USER)
    target = f"/api/identities/{identity['id']}"
    forbidden = [
        ordinary.get("/api/identities"), ordinary.get("/api/identities/policy"),
        ordinary.get("/api/identities/events"),
        ordinary.post("/api/identities", json=payload("Outro")),
        ordinary.patch(target, json={"active": False}),
        ordinary.post(f"{target}/enrollment", headers=JSON),
        ordinary.delete(f"{target}/enrollment", headers=JSON),
        ordinary.post(f"{target}/consent/revoke", headers=JSON),
        ordinary.delete(target, headers=JSON),
        ordinary.post("/api/recognition/simulate",
                      json={"scenario": "match", "identity_id": identity["id"]}),
    ]
    assert {response.status_code for response in forbidden} == {403}
    assert door(client)["secured"]
    assert client.get("/api/identities").json()["items"][0]["state"] == "ready"


def test_policy_and_creation_rules(lab):
    client, _, _ = lab
    policy = client.get("/api/identities/policy").json()
    assert policy["version"] == CONSENT_VERSION and policy["stores_biometric_data"] is False
    assert "simulado" in policy["text"] and policy["retention"]["max_days"] == 365

    invalid = [
        {**payload(), "consent": False},
        {k: v for k, v in payload().items() if k != "consent"},
        {**payload(), "consent": "sim"},
        {**payload(), "retention_days": 0}, {**payload(), "retention_days": 366},
        {**payload(), "retention_days": "30"},
        payload("@@"), payload("a"), payload("x" * 61),
        payload(days=[]), payload(days=[9]), payload(start="8h", end="18:00"),
        payload(start="08:00", end="08:00"), payload(start="24:00", end="12:00"),
        {**payload(), "extra": 1}, {**payload(), "active": True},
    ]
    for body in invalid:
        assert client.post("/api/identities", json=body).status_code == 422, body
    assert client.get("/api/identities").json()["items"] == []

    stale = client.post("/api/identities", json={**payload(), "consent_version": "1999-01-01"})
    assert stale.status_code == 409
    assert client.get("/api/identities").json()["items"] == []

    created = create(client, "  Aluno   01 ", retention_days=7, days=[3, 1, 1],
                     start="08:00", end="18:00")
    assert created["label"] == "Aluno 01" and created["state"] == "not_enrolled"
    assert created["schedule"] == {"days": [1, 3], "start": "08:00", "end": "18:00"}
    assert created["consent"]["recorded_by"] == "admin"
    assert created["consent"]["version"] == CONSENT_VERSION
    assert created["expires_at"] == created["consent"]["granted_at"] + 7 * 86400
    assert created["access_now"]["code"] == "not_enrolled"

    duplicate = client.post("/api/identities", json=payload("aluno 01"))
    assert duplicate.status_code == 409


def test_cross_origin_and_json_boundaries_apply_to_identities(lab):
    client, _, _ = lab
    identity = create(client)
    target = f"/api/identities/{identity['id']}"
    hostile = client.post("/api/identities", json=payload("Outro"),
                          headers={"Origin": "https://outro-site.example"})
    assert hostile.status_code == 403
    assert client.delete(target).status_code == 415
    assert client.get("/api/identities").json()["items"][0]["id"] == identity["id"]


def test_update_rules(lab):
    client, _, _ = lab
    identity = create(client)
    target = f"/api/identities/{identity['id']}"
    for body in ({}, {"days": [1]}, {"start": "08:00"}, {"days": [1], "start": "08:00"},
                 {"active": "sim"}, {"days": [1], "start": "09:00", "end": "09:00"},
                 {"label": "Novo nome"}):
        assert client.patch(target, json=body).status_code == 422, body
    assert client.patch("/api/identities/999", json={"active": False}).status_code == 404
    assert client.patch("/api/identities/0", json={"active": False}).status_code == 422
    changed = client.patch(target, json={"days": [0, 1], "start": "22:00", "end": "06:00"})
    assert changed.status_code == 200
    assert changed.json()["schedule"] == {"days": [0, 1], "start": "22:00", "end": "06:00"}
    disabled = client.patch(target, json={"active": False}).json()
    assert disabled["state"] == "inactive" and not disabled["active"]


# --- Reconhecimento simulado ------------------------------------------------------------


def test_authorized_identity_releases_lock_but_never_opens_door(lab):
    client, _, _ = lab
    identity = ready(client, "Aluno Secreto")
    response = match(client, identity["id"])
    body = response.json()
    assert response.status_code == 200 and body["ok"] and body["simulated"]
    assert body["identity_id"] == identity["id"]
    assert body["state"]["door"]["lock"] == "released"
    assert body["state"]["door"]["position"] == "closed"
    latest = client.get("/api/events?limit=1").json()["items"][0]
    assert latest["type"] == "unlock" and latest["source"] == "recognition"
    assert latest["actor"] == "admin" and latest["outcome"] == "success"
    assert "simulado" in latest["detail"] and f"#{identity['id']}" in latest["detail"]
    # Uma segunda tentativa durante a liberação não amplia o prazo.
    again = match(client, identity["id"])
    assert again.status_code == 409 and again.json()["code"] == "already_released"


@pytest.mark.parametrize("prepare", ["not_enrolled", "inactive", "schedule"])
def test_unauthorized_identity_never_releases_lock(lab, prepare):
    client, _, _ = lab
    if prepare == "not_enrolled":
        identity, code = create(client), "not_enrolled"
    elif prepare == "inactive":
        identity, code = ready(client), "identity_inactive"
        client.patch(f"/api/identities/{identity['id']}", json={"active": False})
    else:
        identity = ready(client, days=[(today() + 1) % 7])
        code = "outside_schedule"
    response = match(client, identity["id"])
    assert response.status_code == 409 and response.json()["code"] == code
    assert response.json()["simulated"] is True
    assert door(client)["secured"] and door(client)["lock"] == "engaged"
    denied = client.get("/api/events?limit=1").json()["items"][0]
    assert denied["type"] == "recognition_denied" and denied["outcome"] == "denied"
    assert denied["source"] == "recognition" and f"#{identity['id']}" in denied["detail"]


def test_unknown_face_is_denied_and_recorded(lab):
    client, _, _ = lab
    ready(client)
    response = client.post("/api/recognition/simulate", json={"scenario": "no_match"})
    assert response.status_code == 409 and response.json()["code"] == "no_match"
    assert door(client)["secured"]
    assert event_types(client)[0] == "recognition_no_match"


def test_recognition_payload_validation(lab):
    client, _, _ = lab
    identity = ready(client)
    for body in ({}, {"scenario": "match"}, {"scenario": "no_match", "identity_id": 1},
                 {"scenario": "adivinhar"}, {"scenario": "match", "identity_id": 0},
                 {"scenario": "match", "identity_id": "1"},
                 {"scenario": "match", "identity_id": identity["id"], "score": 0.99}):
        assert client.post("/api/recognition/simulate", json=body).status_code == 422, body
    assert match(client, 999).status_code == 404
    assert door(client)["secured"]


def test_open_door_and_powered_off_device_block_the_release(lab):
    client, _, _ = lab
    identity = ready(client)
    assert client.post("/api/actions", json={"action": "key_entry"}).status_code == 200
    blocked = match(client, identity["id"])
    assert blocked.status_code == 409 and blocked.json()["code"] == "door_open"
    assert door(client)["position"] == "open"
    assert client.post("/api/actions", json={"action": "close"}).status_code == 200

    assert client.post("/api/simulation/power", json={"mains_available": False}).status_code == 200
    assert client.post("/api/simulation/clock", json={"paused": True}).status_code == 200
    assert client.post("/api/simulation/clock", json={"advance_seconds": 21600}).status_code == 200
    off = match(client, identity["id"])
    assert off.status_code == 409 and off.json()["code"] == "device_powered_off"
    assert door(client)["lock"] == "engaged"
    assert client.post("/api/actions", json={"action": "exit"}).status_code == 200


# --- Consentimento, exclusão e retenção -------------------------------------------------


def test_revoking_consent_erases_enrollment_and_blocks_access(lab):
    client, _, _ = lab
    identity = ready(client)
    target = f"/api/identities/{identity['id']}"
    revoked = client.post(f"{target}/consent/revoke", headers=JSON)
    assert revoked.status_code == 200
    body = revoked.json()
    assert body["state"] == "revoked" and body["enrollment"] == "none"
    assert body["enrolled_at"] is None and body["consent"]["revoked_at"] is not None
    denied = match(client, identity["id"])
    assert denied.status_code == 409 and denied.json()["code"] == "consent_revoked"
    assert door(client)["secured"]
    assert client.post(f"{target}/enrollment", headers=JSON).status_code == 409
    assert client.patch(target, json={"active": True}).status_code == 409
    assert client.post(f"{target}/consent/revoke", headers=JSON).status_code == 409


def test_enrollment_can_be_removed_and_registered_again(lab):
    client, _, _ = lab
    identity = ready(client)
    target = f"/api/identities/{identity['id']}"
    assert client.post(f"{target}/enrollment", headers=JSON).status_code == 409
    removed = client.delete(f"{target}/enrollment", headers=JSON)
    assert removed.status_code == 200 and removed.json()["state"] == "not_enrolled"
    assert client.delete(f"{target}/enrollment", headers=JSON).status_code == 409
    assert match(client, identity["id"]).json()["code"] == "not_enrolled"
    assert client.post(f"{target}/enrollment", headers=JSON).status_code == 201
    assert match(client, identity["id"]).status_code == 200


def test_deletion_leaves_no_label_and_no_access(lab):
    client, _, _ = lab
    label = "Fulano Exclusivo"
    identity = ready(client, label)
    assert match(client, identity["id"]).status_code == 200
    target = f"/api/identities/{identity['id']}"
    assert client.delete(target, headers=JSON).status_code == 200
    assert client.get("/api/identities").json()["items"] == []
    assert client.delete(target, headers=JSON).status_code == 404
    assert match(client, identity["id"]).status_code == 404
    audit = client.get("/api/identities/events").json()["items"]
    assert [item["type"] for item in audit][:3] == [
        "identity_deleted", "enrollment_simulated", "identity_created",
    ]
    everything = json.dumps([audit, client.get("/api/events?limit=100").json(),
                             client.get("/api/auth/events").json()], ensure_ascii=False)
    assert label not in everything and "Fulano" not in everything
    # O número não é reaproveitado, então "Identidade #n" nunca aponta para outra pessoa.
    assert create(client, "Outra pessoa")["id"] > identity["id"]


def test_retention_deletes_identities_when_time_ends(lab):
    client, wall, _ = lab
    short = create(client, "Prazo curto", retention_days=1)
    create(client, "Prazo longo", retention_days=30)
    wall[0] = EPOCH + 86400 - 1
    login(client)
    assert [item["label"] for item in client.get("/api/identities").json()["items"]] == [
        "Prazo curto", "Prazo longo",
    ]
    wall[0] = EPOCH + 86400
    login(client)
    assert [item["label"] for item in client.get("/api/identities").json()["items"]] == [
        "Prazo longo",
    ]
    assert match(client, short["id"]).status_code == 404
    purged = client.get("/api/identities/events").json()["items"][0]
    assert purged["type"] == "retention_purged" and purged["actor"] is None
    assert f"#{short['id']}" in purged["detail"] and "Prazo curto" not in purged["detail"]


def test_identities_survive_restart_and_retention_applies_at_startup(tmp_path):
    path = tmp_path / "restart.sqlite3"
    wall = [EPOCH]
    with TestClient(create_app(path, clock=lambda: 0, session_clock=lambda: wall[0]),
                    base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        login(client)
        identity = ready(client, "Persistente", retention_days=2)
        assert match(client, identity["id"]).status_code == 200

    wall[0] = EPOCH + 3600
    with TestClient(create_app(path, clock=lambda: 0, session_clock=lambda: wall[0]),
                    base_url="http://localhost") as client:
        login(client)
        items = client.get("/api/identities").json()["items"]
        assert len(items) == 1 and items[0]["state"] == "ready"
        # Reiniciar nunca retoma a liberação anterior.
        assert door(client)["lock"] == "engaged"

    wall[0] = EPOCH + 3 * 86400
    with TestClient(create_app(path, clock=lambda: 0, session_clock=lambda: wall[0]),
                    base_url="http://localhost") as client:
        login(client)
        assert client.get("/api/identities").json()["items"] == []
        assert client.get("/api/identities/events").json()["items"][0]["type"] == (
            "retention_purged"
        )


# --- Separação das contas e ausência de dados biométricos -------------------------------


def test_identities_are_separate_from_accounts(lab):
    client, _, app = lab
    identity = ready(client, "maria")  # mesmo texto de uma conta, sem relação com ela
    assert client.post("/api/auth/users", json={**USER, "role": "user"}).status_code == 201
    users = client.get("/api/auth/users").json()["items"]
    maria = next(item for item in users if item["username"] == "maria")
    assert client.patch(f"/api/auth/users/{maria['id']}",
                        json={"role": "user", "active": False}).status_code == 200
    assert match(client, identity["id"]).status_code == 200
    columns = {row["name"] for row in app.state.controller.storage.connection.execute(
        "PRAGMA table_info(identities)")}
    assert "user_id" not in columns and "username" not in columns


def test_no_image_is_ever_stored_and_vectors_live_apart_from_identities(lab):
    client, _, app = lab
    ready(client)
    db = app.state.controller.storage.connection
    listing = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in listing]
    columns = {(table, row["name"], row["type"].upper()) for table in tables
               for row in db.execute(f"PRAGMA table_info({table})")}
    forbidden = ("image", "photo", "foto", "imagem", "picture", "frame")
    assert not [item for item in columns if any(word in item[1].lower() for word in forbidden)]
    # Os vetores cifrados ficam só em face_templates; a tabela de identidades não tem BLOB.
    assert not [name for table, name, kind in columns if table == "identities" and kind == "BLOB"]
    assert ("face_templates", "sealed", "BLOB") in columns
    # Sem motor facial (sem modelos), o app declara que não guarda dado biométrico.
    assert client.get("/api/identities/policy").json()["stores_biometric_data"] is False
    assert client.get("/api/status").json()["capabilities"]["face_recognition"] is False
