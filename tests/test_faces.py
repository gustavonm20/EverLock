import base64

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.accounts import SESSION_SECONDS
from everlock.app import create_app
from everlock.biometrics import TemplateVault, cosine, pack, unpack
from everlock.faces import MAX_IMAGE_BYTES, FaceError, OpenCVFaceEngine, UnavailableEngine
from everlock.identities import CONSENT_VERSION

EPOCH = 1_790_000_000.0
ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
JSON = {"Content-Type": "application/json"}


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def photos(name, count=5):
    return [b64(f"PESSOA:{name}:{n}") for n in range(count)]


@pytest.fixture
def lab(tmp_path):
    wall = [EPOCH]
    app = create_app(tmp_path / "faces.sqlite3", clock=lambda: 0, session_clock=lambda: wall[0],
                     face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        yield client, wall, app, tmp_path


def create(client, label, **extra):
    body = {"label": label, "consent": True, "consent_version": CONSENT_VERSION, **extra}
    response = client.post("/api/identities", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def enroll(client, label, person=None, **extra):
    identity = create(client, label, **extra)
    response = client.post(f"/api/identities/{identity['id']}/face",
                           json={"images": photos(person or label)})
    assert response.status_code == 201, response.text
    return identity


def verify(client, text, *, turn=None, turned_person=None, challenge=None, front_yaw=0.0):
    reply = client.post("/api/recognition/challenge", json={}) if challenge is None else None
    if reply is not None and reply.status_code != 200:
        return reply
    challenge = challenge or reply.json()
    sign = 1 if challenge["direction"] == "left" else -1
    yaw = sign * 0.30 if turn is None else turn
    parts = text.split(":")
    front = f"{text}:{front_yaw}" if parts[0] == "PESSOA" and len(parts) == 3 else text
    if turned_person is None and parts[0] == "PESSOA" and len(parts) >= 2:
        turned_person = parts[1]
    turned_person = turned_person or "movimento"
    body = {
        "challenge_id": challenge["challenge_id"],
        "front": b64(front),
        "turned": [b64(f"PESSOA:{turned_person}:giro{n}:{yaw}") for n in range(3)],
    }
    return client.post("/api/recognition/verify", json=body)


def lock(client):
    return client.get("/api/status").json()["door"]["lock"]


def count(app, table="face_templates"):
    return app.state.identities.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- vetores, cofre e motor ----------------------------------------------------------------


def test_vector_helpers_and_vault(tmp_path):
    vector = FakeFaceEngine._unit("a")
    assert unpack(pack(vector)) == pytest.approx(vector, abs=1e-6)
    assert cosine(vector, vector) == pytest.approx(1.0)
    assert cosine(vector, [-value for value in vector]) == pytest.approx(-1.0)
    assert cosine([0.0] * 128, vector) == 0.0
    for bad in ([1.0] * 127, [float("nan")] * 128):
        with pytest.raises(ValueError):
            pack(bad)
    with pytest.raises(ValueError):
        unpack(b"curto")

    vault = TemplateVault(tmp_path / "chave.bin")
    assert not (tmp_path / "chave.bin").exists()  # criada só no primeiro uso
    sealed = vault.seal(1, vector)
    assert pack(vector) not in sealed and len(vault.key_path.read_bytes()) == 32
    assert vault.open(1, sealed) == pytest.approx(vector, abs=1e-6)
    assert vault.seal(1, vector) != sealed  # nonce novo a cada vez
    with pytest.raises(ValueError):
        vault.open(2, sealed)  # amarrado à identidade 1
    with pytest.raises(ValueError):
        vault.open(1, sealed[:-1] + bytes([sealed[-1] ^ 1]))  # adulterado
    vault.key_path.write_bytes(b"outra chave qualquer de 32 bytes!!")
    with pytest.raises(RuntimeError):
        TemplateVault(vault.key_path).seal(1, vector)


def test_opencv_engine_reports_missing_models_instead_of_crashing(tmp_path):
    engine = OpenCVFaceEngine(tmp_path / "sem-modelos")
    assert not engine.available and "Modelos" in engine.reason or "OpenCV" in engine.reason
    with pytest.raises(FaceError) as error:
        engine.read(b"qualquer coisa")
    assert error.value.code == "engine_unavailable"
    assert UnavailableEngine("x").available is False


# --- estado e permissões --------------------------------------------------------------------


def test_status_capabilities_and_permissions(lab):
    client, _, app, _ = lab
    status = client.get("/api/faces/status").json()
    assert status["available"] and status["stores_images"] is False
    assert status["samples"] == {"min": 3, "max": 5} and 0.3 < status["match_threshold"] < 1
    assert status["liveness"]["required"] is True
    assert client.get("/api/status").json()["capabilities"]["face_recognition"] is True
    assert client.get("/api/identities/policy").json()["stores_biometric_data"] is True

    identity = create(client, "Ana")
    person = {"username": "pessoa", "email": "pessoa@example.com", "password": "Ab1@cd"}
    assert client.post("/api/auth/users", json={**person, "role": "user"}).status_code == 201
    anonymous = TestClient(app, base_url="http://localhost")
    valid_verify = {"challenge_id": "x" * 20, "front": b64("PESSOA:ana:1"),
                    "turned": [b64("PESSOA:ana:2:0.3")]}
    calls = [("get", "/api/faces/status", None),
             ("post", "/api/recognition/challenge", {}),
             ("post", f"/api/identities/{identity['id']}/face", {"images": photos("ana", 3)}),
             ("post", "/api/recognition/verify", valid_verify)]
    for method, path, body in calls:
        assert getattr(anonymous, method)(path, **({"json": body} if body is not None else {})
                                          ).status_code == 401
    credentials = {"identifier": "pessoa", "password": "Ab1@cd"}
    assert anonymous.post("/api/auth/login", json=credentials).status_code == 200
    for method, path, body in calls:
        assert getattr(anonymous, method)(path, **({"json": body} if body is not None else {})
                                          ).status_code == 403


def test_unavailable_engine_disables_everything_safely(tmp_path):
    app = create_app(tmp_path / "off.sqlite3", face_engine=UnavailableEngine("sem modelos"))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        identity = create(client, "Ana")
        assert client.get("/api/faces/status").json() == {
            **client.get("/api/faces/status").json(), "available": False, "reason": "sem modelos"}
        assert client.get("/api/status").json()["capabilities"]["face_recognition"] is False
        assert client.get("/api/identities/policy").json()["stores_biometric_data"] is False
        enrolled = client.post(f"/api/identities/{identity['id']}/face",
                               json={"images": photos("ana", 3)})
        assert enrolled.status_code == 503 and "sem modelos" in enrolled.json()["message"]
        assert verify(client, "PESSOA:ana:1").status_code == 503
        assert lock(client) == "engaged"


# --- cadastro facial ------------------------------------------------------------------------


def test_enrollment_stores_only_sealed_vectors(lab):
    client, _, app, tmp_path = lab
    assert not (tmp_path / "biometria.chave").exists()
    identity = enroll(client, "Ana")
    body = client.get("/api/identities").json()["items"][0]
    assert body["id"] == identity["id"] and body["enrollment"] == "face"
    assert body["face_samples"] == 5 and body["state"] == "ready"
    assert body["access_now"]["code"] == "authorized"
    assert count(app) == 5 and (tmp_path / "biometria.chave").stat().st_size == 32
    db = app.state.identities.db
    for row in db.execute("SELECT sealed FROM face_templates"):
        vector = FakeFaceEngine().read(b"PESSOA:ana:0").embedding
        assert pack(vector) not in row["sealed"] and len(row["sealed"]) == 12 + 512 + 16
    audit = client.get("/api/identities/events").text
    assert "face_enrolled" in audit and "5 amostras" in audit and "Ana" not in audit
    # Refazer substitui as amostras anteriores, sem acumular.
    again = client.post(f"/api/identities/{identity['id']}/face", json={"images": photos("ana", 3)})
    assert again.status_code == 201 and count(app) == 3


def test_enrollment_rejects_bad_samples(lab):
    client, _, app, _ = lab
    identity = create(client, "Ana")
    target = f"/api/identities/{identity['id']}/face"
    assert client.post(target, json={"images": photos("ana", 2)}).status_code == 422
    assert client.post(target, json={"images": photos("ana", 6)}).status_code == 422
    assert client.post(target, json={"images": ["###"] * 3}).status_code == 422
    assert client.post(target, json={"images": photos("ana"), "x": 1}).status_code == 422
    missing = client.post("/api/identities/999/face", json={"images": photos("ana")})
    assert missing.status_code == 404

    few = [b64("PESSOA:ana:1"), b64("PESSOA:ana:2"), b64("SEMROSTO"), b64("BORRADO"),
           b64("DOISROSTOS")]
    response = client.post(target, json={"images": few})
    assert response.status_code == 422 and response.json()["code"] == "not_enough_samples"
    mixed = [b64("PESSOA:ana:1"), b64("PESSOA:ana:2"), b64("PESSOA:bia:1")]
    response = client.post(target, json={"images": mixed})
    assert response.status_code == 422 and response.json()["code"] == "inconsistent_samples"
    assert count(app) == 0 and client.get("/api/identities").json()["items"][0]["face_samples"] == 0


def test_same_face_cannot_be_enrolled_twice(lab):
    client, _, app, _ = lab
    first = enroll(client, "Ana", "ana")
    second = create(client, "Ana Duplicada")
    response = client.post(f"/api/identities/{second['id']}/face", json={"images": photos("ana")})
    assert response.status_code == 409 and response.json()["code"] == "face_already_enrolled"
    assert f"#{first['id']}" in response.json()["message"] and count(app) == 5
    assert client.post(f"/api/identities/{first['id']}/face",
                       json={"images": photos("ana")}).status_code == 201  # a própria identidade


def test_identity_with_old_consent_text_cannot_enroll_a_face(lab):
    client, _, app, _ = lab
    identity = create(client, "Antiga")
    app.state.identities.db.execute("UPDATE identities SET consent_version='2026-09-29'")
    response = client.post(f"/api/identities/{identity['id']}/face", json={"images": photos("x")})
    assert response.status_code == 409 and "termo" in response.json()["detail"]
    assert client.get("/api/identities").json()["items"][0]["face_consent_ok"] is False


# --- reconhecimento -------------------------------------------------------------------------


def test_recognized_authorized_face_releases_lock_but_not_door(lab):
    client, _, _, _ = lab
    ana = enroll(client, "Ana Secreta", "ana")
    enroll(client, "Bia", "bia")
    response = verify(client, "PESSOA:ana:42")
    body = response.json()
    assert response.status_code == 200 and body["ok"] and body["simulated"] is False
    assert body["identity_id"] == ana["id"] and body["similarity"] > 0.9
    assert body["state"]["door"]["lock"] == "released" and body["state"]["door"]["secured"] is False
    assert body["state"]["door"]["position"] == "closed"
    assert "Ana Secreta" not in response.text
    event = client.get("/api/events?limit=1").json()["items"][0]
    assert event["source"] == "recognition" and "reconhecimento facial" in event["title"]
    assert event["actor"] == "admin"
    assert f"#{ana['id']}" in event["detail"] and "Ana Secreta" not in event["detail"]
    assert verify(client, "PESSOA:ana:43").json()["code"] == "already_released"


def test_unknown_or_ambiguous_faces_are_refused(lab):
    client, _, _, _ = lab
    enroll(client, "Ana", "ana")
    enroll(client, "Bia", "bia")
    unknown = verify(client, "PESSOA:carlos:1")
    assert unknown.status_code == 409 and unknown.json()["code"] == "no_match"
    assert "Face não cadastrada" in unknown.json()["message"]
    ambiguous = verify(client, "MISTURA:ana:bia:1", turned_person="ana")
    assert ambiguous.status_code == 409 and ambiguous.json()["code"] == "ambiguous"
    assert lock(client) == "engaged"
    kinds = [item["type"] for item in client.get("/api/events?limit=5").json()["items"]]
    assert "recognition_no_match" in kinds and "recognition_ambiguous" in kinds


def test_capture_problems_are_not_access_attempts(lab):
    client, _, _, _ = lab
    enroll(client, "Ana", "ana")
    for text, code in (("SEMROSTO", "no_face"), ("DOISROSTOS", "multiple_faces"),
                       ("BORRADO", "blurry"), ("lixo", "invalid_image")):
        response = verify(client, text)
        assert response.status_code == 422 and response.json()["code"] == code
    challenge = client.post("/api/recognition/challenge", json={}).json()
    invalid = {"challenge_id": challenge["challenge_id"], "front": "@@@",
               "turned": [b64("PESSOA:ana:1:0.3")]}
    assert client.post("/api/recognition/verify", json=invalid).status_code == 422
    # Nada disso conta para o bloqueio nem vira evento de acesso recusado.
    assert verify(client, "PESSOA:ana:1").status_code == 200
    assert "recognition_denied" not in client.get("/api/events?limit=20").text


def test_movement_challenge_is_required_single_use_and_checks_the_same_face(lab):
    client, wall, _, _ = lab
    enroll(client, "Ana", "ana")

    still = verify(client, "PESSOA:ana:1", turn=0.0)
    assert still.status_code == 409 and still.json()["code"] == "liveness_failed"
    assert lock(client) == "engaged"

    challenge = client.post("/api/recognition/challenge", json={}).json()
    wrong_sign = -0.30 if challenge["direction"] == "left" else 0.30
    wrong_way = verify(client, "PESSOA:ana:1", turn=wrong_sign, challenge=challenge)
    assert wrong_way.json()["code"] == "liveness_failed"
    reused = verify(client, "PESSOA:ana:1", challenge=challenge)
    assert reused.status_code == 409 and reused.json()["code"] == "challenge_expired"

    crooked = verify(client, "PESSOA:ana:1", front_yaw=0.40)
    assert crooked.json()["code"] == "liveness_failed"
    changed = verify(client, "PESSOA:ana:1", turned_person="bia")
    assert changed.json()["code"] == "face_changed"

    expired = client.post("/api/recognition/challenge", json={}).json()
    wall[0] += 46
    assert verify(client, "PESSOA:ana:1", challenge=expired).json()["code"] == "challenge_expired"
    wall[0] += 61  # encerra também o bloqueio acumulado pelas recusas acima
    assert verify(client, "PESSOA:ana:1").status_code == 200


@pytest.mark.parametrize("change", ["expires", "comparison_expires", "cancelled", "replaced",
                                   "logout"])
def test_challenge_is_revalidated_before_release(lab, monkeypatch, change):
    client, wall, app, _ = lab
    enroll(client, "Ana", "ana")
    challenge = client.post("/api/recognition/challenge", json={}).json()
    original_read, changed = app.state.recognition.engine.read, False

    def read(image):
        nonlocal changed
        reading = original_read(image)
        if not changed:
            changed = True
            if change == "expires":
                wall[0] += 46
            elif change == "cancelled":
                path = f"/api/recognition/challenge/{challenge['challenge_id']}"
                assert client.delete(path, headers=JSON).status_code == 200
            elif change == "replaced":
                assert client.post("/api/recognition/challenge", json={}).status_code == 200
            elif change == "logout":
                assert client.post("/api/auth/logout", headers=JSON).status_code == 200
        return reading

    monkeypatch.setattr(app.state.recognition.engine, "read", read)
    if change == "comparison_expires":
        original_scores = app.state.recognition._scores

        def scores(vector, candidates):
            ranked = original_scores(vector, candidates)
            wall[0] += 46
            return ranked

        monkeypatch.setattr(app.state.recognition, "_scores", scores)
    response = verify(client, "PESSOA:ana:1", challenge=challenge)
    assert response.status_code == (401 if change == "logout" else 409)
    if change != "logout":
        assert response.json()["code"] == "challenge_expired"
    assert app.state.controller.status()["door"]["lock"] == "engaged"


def test_challenge_belongs_to_its_session_and_cannot_be_replayed_while_processing(lab,
                                                                                monkeypatch):
    client, _, app, _ = lab
    enroll(client, "Ana", "ana")
    challenge = client.post("/api/recognition/challenge", json={}).json()
    person = {"username": "outro", "email": "outro@example.com", "password": "Ab1@cd"}
    assert client.post("/api/auth/users", json={**person, "role": "admin"}).status_code == 201
    other = TestClient(app, base_url="http://localhost")
    assert other.post("/api/auth/login", json={"identifier": "outro", "password": "Ab1@cd"}
                      ).status_code == 200
    assert verify(other, "PESSOA:ana:1", challenge=challenge).json()["code"] == "challenge_expired"
    path = f"/api/recognition/challenge/{challenge['challenge_id']}"
    # Não cancela o desafio de outra sessão.
    assert other.delete(path, headers=JSON).status_code == 200

    original_read, replayed = app.state.recognition.engine.read, False

    def read(image):
        nonlocal replayed
        if not replayed:
            replayed = True
            replay = verify(client, "PESSOA:ana:1", challenge=challenge)
            assert replay.status_code == 409 and replay.json()["code"] == "challenge_expired"
        return original_read(image)

    monkeypatch.setattr(app.state.recognition.engine, "read", read)
    assert verify(client, "PESSOA:ana:1", challenge=challenge).status_code == 200
    assert verify(client, "PESSOA:ana:1", challenge=challenge).json()["code"] == "challenge_expired"


@pytest.mark.parametrize("change,status,code", [
    ("challenge_expires", 409, "challenge_expired"),
    ("session_expires", 401, None),
    ("schedule_ends", 409, "outside_schedule"),
    ("retention_expires", 404, None),
])
def test_sync_before_actuation_revalidates_face_authorization(lab, monkeypatch, change,
                                                            status, code):
    from datetime import datetime, timedelta

    client, wall, app, _ = lab
    identity = enroll(client, "Ana", "ana", retention_days=1)
    advance = 46 if change == "challenge_expires" else 2
    if change == "session_expires":
        wall[0] += SESSION_SECONDS - 1
    elif change == "retention_expires":
        wall[0] += 86400 - 1
        login = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=login).status_code == 200
    elif change == "schedule_ends":
        local = datetime.fromtimestamp(wall[0])
        end = local + timedelta(minutes=1)
        last = "24:00" if end.date() != local.date() else end.strftime("%H:%M")
        schedule = {"days": [local.weekday()], "start": "00:00", "end": last}
        assert client.patch(f"/api/identities/{identity['id']}", json=schedule).status_code == 200
        wall[0] += 59 - local.second
    challenge = client.post("/api/recognition/challenge", json={}).json()
    controller = app.state.controller
    original_release, original_sync = controller.recognition_release, controller._sync
    releasing, advanced = False, False

    def sync():
        nonlocal advanced
        original_sync()
        if releasing and not advanced:
            wall[0] += advance
            advanced = True

    def release(*args, **kwargs):
        nonlocal releasing
        releasing = True
        try:
            return original_release(*args, **kwargs)
        finally:
            releasing = False

    monkeypatch.setattr(controller, "_sync", sync)
    monkeypatch.setattr(controller, "recognition_release", release)
    response = verify(client, "PESSOA:ana:1", challenge=challenge)
    assert advanced and response.status_code == status, response.text
    if code is not None:
        assert response.json()["code"] == code
    assert controller.status()["door"]["secured"]
    assert not any(event["type"] == "unlock" for event in controller.events(100))
    if change == "retention_expires":
        assert count(app) == 0


def test_mixed_faces_during_the_turn_and_oversized_images_are_refused(lab):
    client, _, _, _ = lab
    enroll(client, "Ana", "ana")
    challenge = client.post("/api/recognition/challenge", json={}).json()
    yaw = 0.30 if challenge["direction"] == "left" else -0.30
    body = {"challenge_id": challenge["challenge_id"], "front": b64("PESSOA:ana:1"),
            "turned": [b64(f"PESSOA:{person}:2:{yaw}") for person in ("ana", "bia", "ana")]}
    response = client.post("/api/recognition/verify", json=body)
    assert response.status_code == 409 and response.json()["code"] == "face_changed"
    assert lock(client) == "engaged"
    body["front"] = base64.b64encode(b"a" * (MAX_IMAGE_BYTES + 1)).decode()
    assert client.post("/api/recognition/verify", json=body).status_code == 413
    body["front"] = b64("PESSOA:ana:1")
    body["turned"] *= 3
    assert client.post("/api/recognition/verify", json=body).status_code == 422


def test_repeated_failures_lock_attempts_for_a_while(lab):
    client, wall, _, _ = lab
    enroll(client, "Ana", "ana")
    for number in range(5):
        assert verify(client, f"PESSOA:intruso:{number}").json()["code"] == "no_match"
    blocked = verify(client, "PESSOA:ana:1")  # até o rosto certo espera
    assert blocked.status_code == 429 and blocked.json()["code"] == "rate_limited"
    assert lock(client) == "engaged"
    wall[0] += 61
    assert verify(client, "PESSOA:ana:1").status_code == 200


def test_recognized_but_not_authorized_identity_stays_locked(lab):
    client, _, _, _ = lab
    from datetime import datetime
    other_day = (datetime.fromtimestamp(EPOCH).weekday() + 1) % 7
    ana = enroll(client, "Ana", "ana", days=[other_day])
    response = verify(client, "PESSOA:ana:1")
    assert response.status_code == 409 and response.json()["code"] == "outside_schedule"
    assert response.json()["identity_id"] == ana["id"] and lock(client) == "engaged"
    client.patch(f"/api/identities/{ana['id']}", json={"days": list(range(7)),
                                                      "start": "00:00", "end": "24:00"})
    client.patch(f"/api/identities/{ana['id']}", json={"active": False})
    assert verify(client, "PESSOA:ana:2").json()["code"] == "identity_inactive"


# --- apagamento -----------------------------------------------------------------------------


def test_revocation_deletion_and_retention_erase_the_vectors(lab):
    client, wall, app, _ = lab
    revoked, deleted, expiring = (enroll(client, "Revogada", "r"), enroll(client, "Excluida", "e"),
                                  enroll(client, "Vencendo", "v", retention_days=1))
    assert count(app) == 15
    assert client.post(f"/api/identities/{revoked['id']}/consent/revoke",
                       headers=JSON).status_code == 200
    assert count(app) == 10 and verify(client, "PESSOA:r:1").json()["code"] == "no_match"
    assert client.delete(f"/api/identities/{deleted['id']}", headers=JSON).status_code == 200
    assert count(app) == 5
    wall[0] += 86400  # a sessão de 8 horas também vence: entra de novo
    credentials = {"identifier": "admin", "password": ADMIN["password"]}
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    assert [item["id"] for item in client.get("/api/identities").json()["items"]] == [revoked["id"]]
    assert count(app) == 0
    assert expiring["id"] != revoked["id"]


def test_removing_the_enrollment_deletes_face_vectors(lab):
    client, _, app, _ = lab
    ana = enroll(client, "Ana", "ana")
    removed = client.delete(f"/api/identities/{ana['id']}/enrollment", headers=JSON)
    assert removed.status_code == 200 and removed.json()["state"] == "not_enrolled"
    empty = verify(client, "PESSOA:ana:1")  # banco sem nenhuma face
    assert count(app) == 0 and empty.json()["code"] == "no_faces_enrolled"
    assert empty.status_code == 409 and lock(client) == "engaged"


def test_vectors_moved_between_identities_or_keys_are_unusable(lab):
    client, _, app, tmp_path = lab
    ana, bia = enroll(client, "Ana", "ana"), enroll(client, "Bia", "bia")
    db = app.state.identities.db
    move = "UPDATE face_templates SET identity_id=? WHERE identity_id=?"
    db.execute(move, (bia["id"], ana["id"]))
    db.commit()
    assert verify(client, "PESSOA:ana:1").json()["code"] == "no_match"  # amarrados à dona
    db.execute(move, (ana["id"], bia["id"]))
    db.commit()
    (tmp_path / "biometria.chave").unlink()
    app.state.identities.vault._cipher = None  # simula reinício com a chave perdida
    assert verify(client, "PESSOA:ana:1").json()["code"] in {"no_match", "no_faces_enrolled"}
