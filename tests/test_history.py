import csv
import io
from datetime import date, timedelta

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.history import (
    CSV_COLUMNS,
    EventFilter,
    build_where,
    escape_like,
    sanitize_cell,
    to_csv,
    utc_bound,
)

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
TODAY = date.today()


@pytest.fixture
def lab(tmp_path):
    app = create_app(tmp_path / "history.sqlite3", face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        assert client.post("/api/actions", json={"action": "key_entry"}).status_code == 200
        assert client.post("/api/actions", json={"action": "close"}).status_code == 200
        client.post("/api/recognition/simulate", json={"scenario": "no_match"})
        client.post("/api/simulation/power", json={"mains_available": False})
        yield client, app


def items(client, **params):
    response = client.get("/api/events", params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- regras puras -----------------------------------------------------------------------------


def test_where_clause_uses_only_parameters():
    assert build_where(EventFilter()) == ("", [])
    where, params = build_where(EventFilter(outcome="denied", source="recognition",
                                            type="recognition_no_match"))
    assert where == " WHERE outcome = ? AND source = ? AND type = ?"
    assert params == ["denied", "recognition", "recognition_no_match"]
    where, params = build_where(EventFilter(q="' OR 1=1 --"))
    assert "OR 1=1" not in where and params[0] == "%' or 1=1 --%"
    where, params = build_where(EventFilter(since=date(2026, 10, 2), until=date(2026, 10, 2)))
    assert where.count("?") == 2 and params[0] < params[1]
    assert utc_bound(date(2026, 10, 2)).endswith("+00:00")


def test_like_wildcards_are_literal_and_cells_are_neutralized():
    assert escape_like("100%_a\\b") == "100\\%\\_a\\\\b"
    for dangerous in ("=1+1", "+cmd", "-2", "@SUM(A1)", "\tx", "\rx"):
        assert sanitize_cell(dangerous) == "'" + dangerous
    assert sanitize_cell("texto normal") == "texto normal"
    assert sanitize_cell(None) == "" and sanitize_cell(42) == "42"


def test_csv_format_for_excel_in_portuguese():
    row = {"id": 7, "created_at": "2026-10-02T14:03:21.500000+00:00", "simulated_at": 12.5,
           "type": "unlock", "title": "Trava; liberada", "detail": "linha 1\nlinha 2",
           "source": "manual", "outcome": "success", "actor": "=HYPERLINK(\"http://x\")"}
    raw = to_csv([row])
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(raw[3:].decode("utf-8")), delimiter=";"))
    assert tuple(rows[0]) == CSV_COLUMNS and len(rows) == 2
    record = dict(zip(CSV_COLUMNS, rows[1], strict=True))
    assert record["id"] == "7" and record["tempo_virtual_s"] == "12,5"
    assert record["titulo"] == "Trava; liberada" and record["detalhe"] == "linha 1\nlinha 2"
    assert record["usuario"].startswith("'=") and record["data_hora_utc"].endswith("+00:00")
    assert len(record["data_hora_local"]) == 19


# --- filtros na API -----------------------------------------------------------------------------


def test_filters_by_outcome_source_type_and_text(lab):
    client, _ = lab
    everything = items(client)
    assert len(everything) >= 4
    denied = items(client, outcome="denied")
    assert denied and all(item["outcome"] == "denied" for item in denied)
    assert {item["source"] for item in items(client, source="recognition")} == {"recognition"}
    only_type = items(client, type="recognition_no_match")
    assert only_type and all(item["type"] == "recognition_no_match" for item in only_type)
    assert items(client, q="DESCONHECIDO")  # sem diferenciar maiúsculas
    assert items(client, q="admin")  # procura também no usuário
    assert items(client, q="texto que nunca aparece") == []
    assert items(client, q="%") == [] and items(client, q="_") == []  # curingas são literais
    both = items(client, outcome="denied", source="recognition")
    assert both and all(i["outcome"] == "denied" and i["source"] == "recognition" for i in both)
    assert len(items(client, limit=2)) == 2


def test_date_filters_use_local_days_inclusively(lab):
    client, _ = lab
    total = len(items(client))
    assert len(items(client, since=TODAY.isoformat())) == total
    assert len(items(client, until=TODAY.isoformat())) == total
    assert len(items(client, since=TODAY.isoformat(), until=TODAY.isoformat())) == total
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    assert items(client, since=tomorrow) == []
    assert items(client, until=yesterday) == []


def test_invalid_filters_are_refused(lab):
    client, _ = lab
    bad = [{"outcome": "Denied!"}, {"source": "a b"}, {"type": "x" * 49}, {"q": "x" * 81},
           {"q": ""}, {"since": "ontem"}, {"until": "2026-13-45"},
           {"since": "2026-10-05", "until": "2026-10-01"}, {"limit": 0}, {"limit": 101}]
    for params in bad:
        assert client.get("/api/events", params=params).status_code == 422, params
    assert client.get("/api/events/export.csv", params={"limit": 5001}).status_code == 422
    injection = items(client, q="'; DROP TABLE events; --")
    assert injection == [] and len(items(client)) >= 4  # a tabela continua inteira


def test_filter_endpoints_are_administrator_only(lab):
    client, app = lab
    person = {"username": "pessoa", "email": "pessoa@example.com", "password": "Ab1@cd"}
    assert client.post("/api/auth/users", json={**person, "role": "user"}).status_code == 201
    anonymous = TestClient(app, base_url="http://localhost")
    for path in ("/api/events", "/api/events/export.csv"):
        assert anonymous.get(path).status_code == 401
    credentials = {"identifier": "pessoa", "password": "Ab1@cd"}
    assert anonymous.post("/api/auth/login", json=credentials).status_code == 200
    for path in ("/api/events", "/api/events/export.csv"):
        assert anonymous.get(path).status_code == 403


# --- exportação ---------------------------------------------------------------------------------


def parse(response):
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(response.content[3:].decode("utf-8")), delimiter=";"))


def test_export_downloads_the_filtered_history(lab):
    client, _ = lab
    response = client.get("/api/events/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="everlock-historico-')
    assert disposition.endswith('.csv"') and response.headers["cache-control"] == "no-store"
    everything = parse(response)
    assert len(everything) == len(items(client)) and list(everything[0]) == list(CSV_COLUMNS)
    denied = parse(client.get("/api/events/export.csv", params={"outcome": "denied"}))
    assert denied and all(row["resultado"] == "denied" for row in denied)
    assert len(parse(client.get("/api/events/export.csv", params={"limit": 2}))) == 2
    assert parse(client.get("/api/events/export.csv", params={"q": "nunca aparece"})) == []


def test_export_neutralizes_formulas_stored_in_events(lab):
    client, app = lab
    db = app.state.controller.storage.connection
    db.execute(
        "INSERT INTO events(type,title,detail,source,outcome,created_at,actor) "
        "VALUES ('teste','=cmd|calc','@SUM(1+1)','manual','info',?, '+55')",
        ("2026-10-02T12:00:00+00:00",),
    )
    db.commit()
    rows = parse(client.get("/api/events/export.csv", params={"q": "cmd"}))
    assert len(rows) == 1
    assert rows[0]["titulo"] == "'=cmd|calc" and rows[0]["detalhe"] == "'@SUM(1+1)"
    assert rows[0]["usuario"] == "'+55"
