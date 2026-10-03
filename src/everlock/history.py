"""Filtros e exportação (CSV) do histórico de eventos da porta e da energia."""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

CSV_COLUMNS = ("id", "data_hora_local", "data_hora_utc", "tempo_virtual_s", "tipo", "titulo",
               "detalhe", "origem", "resultado", "usuario")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class EventFilter:
    outcome: str | None = None
    source: str | None = None
    type: str | None = None
    q: str | None = None
    since: date | None = None  # dia inicial, no fuso deste computador
    until: date | None = None  # dia final, inclusive


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def utc_bound(day: date) -> str:
    """Meia-noite local do dia, convertida para o mesmo formato guardado no banco (UTC)."""
    return datetime.combine(day, time.min).astimezone(UTC).isoformat()


def build_where(filters: EventFilter) -> tuple[str, list]:
    """Cláusula WHERE só com fragmentos fixos e valores em parâmetros (sem texto do usuário)."""
    clauses, params = [], []
    for column, value in (("outcome", filters.outcome), ("source", filters.source),
                          ("type", filters.type)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if filters.q:
        pattern = f"%{escape_like(filters.q.lower())}%"
        clauses.append("(lower(title) LIKE ? ESCAPE '\\' OR lower(detail) LIKE ? ESCAPE '\\' "
                       "OR lower(COALESCE(actor, '')) LIKE ? ESCAPE '\\')")
        params += [pattern, pattern, pattern]
    if filters.since:
        clauses.append("created_at >= ?")
        params.append(utc_bound(filters.since))
    if filters.until:
        clauses.append("created_at < ?")
        params.append(utc_bound(date.fromordinal(filters.until.toordinal() + 1)))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def sanitize_cell(value) -> str:
    """Evita que o Excel execute como fórmula um texto que começa com =, +, - ou @."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def local_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return ""


def to_csv(rows: list[dict]) -> bytes:
    """CSV para o Excel em português: BOM UTF-8 e ponto e vírgula como separador."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        virtual = row.get("simulated_at")
        writer.writerow([
            row["id"], local_time(row["created_at"]), row["created_at"],
            "" if virtual is None else f"{virtual:.1f}".replace(".", ","),
            sanitize_cell(row["type"]), sanitize_cell(row["title"]),
            sanitize_cell(row["detail"]), sanitize_cell(row["source"]),
            sanitize_cell(row["outcome"]), sanitize_cell(row.get("actor")),
        ])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
