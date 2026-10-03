"""Identidades e autorização, separadas das contas de acesso.

O cadastro pode ser um marcador simulado ou vetores faciais cifrados; imagens não persistem.
Consentimento, retenção e horário são consultados antes da atuação. Eventos e auditoria citam
somente o número da identidade, nunca o apelido.
"""

import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException

CONSENT_VERSION = "2026-10-01"
CONSENT_PURPOSE = (
    "Testar a liberação da trava virtual do laboratório EverLock por reconhecimento facial."
)
CONSENT_TEXT = (
    "A pessoa foi informada de que este cadastro serve apenas para testar a liberação da "
    "trava virtual do laboratório EverLock. Ela concordou de forma livre e específica e pode "
    "revogar o consentimento ou pedir a exclusão a qualquer momento. No cadastro facial pela "
    "câmera, as imagens são analisadas na memória e descartadas: somente um vetor numérico do "
    "rosto (dado biométrico) é guardado, cifrado, neste computador. No cadastro simulado nada "
    "é coletado. Ao revogar, excluir ou ao fim do prazo de retenção escolhido, os vetores são "
    "apagados automaticamente."
)
RETENTION_MIN_DAYS = 1
RETENTION_MAX_DAYS = 365
RETENTION_DEFAULT_DAYS = 30
MAX_IDENTITIES = 50
SECONDS_PER_DAY = 86400
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)  # segunda-feira = 0, como em datetime.weekday()

_TIME = re.compile(r"^(?:([01]\d|2[0-3]):([0-5]\d)|(24):00)$")
_LABEL = re.compile(r"^[\w .'-]{2,40}$")


def is_enrolled(identity) -> bool:
    """Cadastrada por marcador simulado ou por vetores faciais reais."""
    return identity["enrollment"] == "simulated" or identity["face_samples"] > 0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    message: str


def parse_time(value: str, *, end: bool) -> int:
    """Converte HH:MM em minutos desde a meia-noite. Só o fim aceita 24:00."""
    match = _TIME.match(value)
    if match is None:
        raise ValueError("Use o formato HH:MM, por exemplo 08:30.")
    minutes = 1440 if match.group(3) else int(match.group(1)) * 60 + int(match.group(2))
    if minutes == 1440 and not end:
        raise ValueError("O início da janela não pode ser 24:00.")
    return minutes


def format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def validate_label(value: str) -> str:
    label = " ".join(value.split())
    if not _LABEL.match(label) or not any(char.isalnum() for char in label):
        raise ValueError(
            "Use de 2 a 40 caracteres: letras, números, espaço, ponto, hífen ou apóstrofo. "
            "Prefira um apelido ou código a um nome completo."
        )
    return label


def validate_schedule(days: list[int], start: str, end: str) -> tuple[str, int, int]:
    if not days or any(type(day) is not int or day not in ALL_DAYS for day in days):
        raise ValueError("Escolha ao menos um dia da semana, de 0 (segunda) a 6 (domingo).")
    first, last = parse_time(start, end=False), parse_time(end, end=True)
    if first == last:
        raise ValueError("O início e o fim da janela de horário precisam ser diferentes.")
    return "".join(str(day) for day in sorted(set(days))), first, last


def within_schedule(days: str, start: int, end: int, local: datetime) -> bool:
    """Janela [início, fim). Se o início for maior que o fim, ela atravessa a meia-noite
    e a parte depois da meia-noite pertence ao dia em que a janela começou."""
    minutes = local.hour * 60 + local.minute
    today = local.weekday()
    if start < end:
        return str(today) in days and start <= minutes < end
    if minutes >= start:
        return str(today) in days
    if minutes < end:
        return str((today - 1) % 7) in days
    return False


def evaluate(identity, now: float) -> Decision:
    """Decisão pura de autorização. Não altera nada e não conhece a porta."""
    if identity["consent_revoked_at"] is not None:
        return Decision(False, "consent_revoked", "O consentimento foi revogado.")
    expires_at = identity["consent_granted_at"] + identity["retention_days"] * SECONDS_PER_DAY
    if now >= expires_at:
        return Decision(False, "retention_expired", "O prazo de retenção terminou.")
    if not identity["active"]:
        return Decision(False, "identity_inactive", "A identidade está desativada.")
    if not is_enrolled(identity):
        return Decision(False, "not_enrolled", "A identidade ainda não tem cadastro.")
    if not within_schedule(
        identity["days"], identity["window_start"], identity["window_end"],
        datetime.fromtimestamp(now),
    ):
        return Decision(False, "outside_schedule", "Fora da janela de horário permitida.")
    return Decision(True, "authorized", "Identidade autorizada neste horário.")


class Identities:
    def __init__(self, connection, mutex, clock=time.time, vault=None):
        self.db, self.mutex, self.clock, self.vault = connection, mutex, clock, vault
        self.biometrics_enabled = False  # a aplicação liga quando motor e cofre existem
        self.notifier = None  # a aplicação liga
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                consent_version TEXT NOT NULL,
                consent_recorded_by TEXT NOT NULL,
                consent_granted_at REAL NOT NULL,
                consent_revoked_at REAL,
                retention_days INTEGER NOT NULL,
                enrollment TEXT NOT NULL DEFAULT 'none'
                    CHECK(enrollment IN ('none', 'simulated')),
                enrolled_at REAL,
                days TEXT NOT NULL,
                window_start INTEGER NOT NULL,
                window_end INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS identity_label ON identities(lower(label));
            CREATE TABLE IF NOT EXISTS identity_events (
                id INTEGER PRIMARY KEY, type TEXT NOT NULL, actor TEXT,
                identity_id INTEGER, detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS face_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_id INTEGER NOT NULL,
                sealed BLOB NOT NULL,
                model TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS face_template_owner ON face_templates(identity_id);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(identities)")}
        if "face_samples" not in columns:
            with self.db:
                self.db.execute(
                    "ALTER TABLE identities ADD COLUMN face_samples INTEGER NOT NULL DEFAULT 0"
                )
        self.purge_expired()

    def audit(self, kind, actor, identity_id, detail):
        self.db.execute(
            "INSERT INTO identity_events(type,actor,identity_id,detail,created_at) "
            "VALUES (?,?,?,?,?)",
            (kind, actor, identity_id, detail, datetime.now(UTC).isoformat()),
        )
        if self.notifier is not None:
            self.notifier.publish(kind, f"Identidade: {kind}", detail, "identities", "info", actor)

    def policy(self):
        return {
            "version": CONSENT_VERSION, "purpose": CONSENT_PURPOSE, "text": CONSENT_TEXT,
            "retention": {"min_days": RETENTION_MIN_DAYS, "max_days": RETENTION_MAX_DAYS,
                          "default_days": RETENTION_DEFAULT_DAYS},
            "stores_biometric_data": self.biometrics_enabled,
        }

    def purge_expired(self) -> int:
        """Aplica a retenção: identidades vencidas são excluídas por completo."""
        with self.mutex:
            rows = self.db.execute(
                "SELECT id FROM identities WHERE consent_granted_at + retention_days * ? <= ?",
                (float(SECONDS_PER_DAY), self.clock()),
            ).fetchall()
            if rows:
                with self.db:
                    for row in rows:
                        self.db.execute("DELETE FROM face_templates WHERE identity_id=?",
                                        (row["id"],))
                        self.db.execute("DELETE FROM identities WHERE id=?", (row["id"],))
                        self.audit("retention_purged", None, row["id"],
                                   f"Identidade #{row['id']} excluída ao fim do prazo de retenção.")
            return len(rows)

    def _row(self, identity_id):
        row = self.db.execute("SELECT * FROM identities WHERE id=?", (identity_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Identidade não encontrada.")
        return row

    def _public(self, row, now):
        decision = evaluate(row, now)
        if row["consent_revoked_at"] is not None:
            state = "revoked"
        elif not row["active"]:
            state = "inactive"
        elif not is_enrolled(row):
            state = "not_enrolled"
        else:
            state = "ready"
        return {
            "id": row["id"], "label": row["label"], "active": bool(row["active"]),
            "state": state, "enrolled_at": row["enrolled_at"],
            "enrollment": "face" if row["face_samples"] else row["enrollment"],
            "face_samples": row["face_samples"],
            "face_consent_ok": row["consent_version"] == CONSENT_VERSION,
            "consent": {
                "version": row["consent_version"], "recorded_by": row["consent_recorded_by"],
                "granted_at": row["consent_granted_at"], "revoked_at": row["consent_revoked_at"],
            },
            "retention_days": row["retention_days"],
            "expires_at": row["consent_granted_at"] + row["retention_days"] * SECONDS_PER_DAY,
            "schedule": {
                "days": [int(day) for day in row["days"]],
                "start": format_time(row["window_start"]), "end": format_time(row["window_end"]),
            },
            "access_now": {"allowed": decision.allowed, "code": decision.code,
                           "message": decision.message},
            "created_at": row["created_at"],
        }

    def list(self):
        with self.mutex:
            self.purge_expired()
            now = self.clock()
            rows = self.db.execute("SELECT * FROM identities ORDER BY id").fetchall()
            return [self._public(row, now) for row in rows]

    def create(self, *, label, retention_days, days, start, end, consent_version, actor):
        with self.mutex:
            self.purge_expired()
            if consent_version != CONSENT_VERSION:
                raise HTTPException(
                    409, "O texto de consentimento mudou. Recarregue a página e confirme de novo.",
                )
            if self.db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] >= MAX_IDENTITIES:
                raise HTTPException(409, f"O laboratório suporta até {MAX_IDENTITIES} identidades.")
            day_text, first, last = validate_schedule(days, start, end)
            now = self.clock()
            try:
                with self.db:
                    cursor = self.db.execute(
                        """INSERT INTO identities
                           (label,consent_version,consent_recorded_by,consent_granted_at,
                            retention_days,days,window_start,window_end,created_by,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (label, CONSENT_VERSION, actor, now, retention_days, day_text, first,
                         last, actor, now),
                    )
                    self.audit("identity_created", actor, cursor.lastrowid,
                               f"Identidade #{cursor.lastrowid} criada com consentimento "
                               f"versão {CONSENT_VERSION}; retenção de {retention_days} dias.")
            except sqlite3.IntegrityError as error:
                raise HTTPException(409, "Já existe uma identidade com esse apelido.") from error
            return self._public(self._row(cursor.lastrowid), now)

    def update(self, identity_id, actor, *, active=None, schedule=None):
        with self.mutex:
            self.purge_expired()
            row = self._row(identity_id)
            if row["consent_revoked_at"] is not None:
                raise HTTPException(
                    409, "O consentimento foi revogado. Exclua a identidade e cadastre de novo.",
                )
            changes = []
            with self.db:
                if active is not None:
                    self.db.execute("UPDATE identities SET active=? WHERE id=?",
                                    (int(active), identity_id))
                    changes.append("ativada" if active else "desativada")
                if schedule is not None:
                    day_text, first, last = validate_schedule(*schedule)
                    self.db.execute(
                        "UPDATE identities SET days=?, window_start=?, window_end=? WHERE id=?",
                        (day_text, first, last, identity_id),
                    )
                    changes.append("janela de horário atualizada")
                self.audit("identity_updated", actor, identity_id,
                           f"Identidade #{identity_id}: {', '.join(changes)}.")
            return self._public(self._row(identity_id), self.clock())

    def enroll(self, identity_id, actor):
        with self.mutex:
            self.purge_expired()
            row = self._row(identity_id)
            if row["consent_revoked_at"] is not None:
                raise HTTPException(409, "O consentimento foi revogado; não é possível cadastrar.")
            if row["enrollment"] == "simulated":
                raise HTTPException(409, "A identidade já tem cadastro simulado.")
            with self.db:
                self.db.execute(
                    "UPDATE identities SET enrollment='simulated', enrolled_at=? WHERE id=?",
                    (self.clock(), identity_id),
                )
                self.audit("enrollment_simulated", actor, identity_id,
                           f"Identidade #{identity_id}: cadastro simulado registrado. "
                           "Nenhuma imagem, vetor ou modelo foi armazenado.")
            return self._public(self._row(identity_id), self.clock())

    def clear_enrollment(self, identity_id, actor):
        with self.mutex:
            self.purge_expired()
            row = self._row(identity_id)
            if not is_enrolled(row):
                raise HTTPException(409, "A identidade não tem cadastro para remover.")
            with self.db:
                self.db.execute("DELETE FROM face_templates WHERE identity_id=?", (identity_id,))
                self.db.execute(
                    "UPDATE identities SET enrollment='none', enrolled_at=NULL, face_samples=0 "
                    "WHERE id=?", (identity_id,),
                )
                self.audit("enrollment_removed", actor, identity_id,
                           f"Identidade #{identity_id}: cadastro removido.")
            return self._public(self._row(identity_id), self.clock())

    def revoke_consent(self, identity_id, actor):
        with self.mutex:
            self.purge_expired()
            row = self._row(identity_id)
            if row["consent_revoked_at"] is not None:
                raise HTTPException(409, "O consentimento já foi revogado.")
            with self.db:
                self.db.execute(
                    """UPDATE identities SET consent_revoked_at=?, enrollment='none',
                       enrolled_at=NULL, face_samples=0 WHERE id=?""",
                    (self.clock(), identity_id),
                )
                self.db.execute("DELETE FROM face_templates WHERE identity_id=?", (identity_id,))
                self.audit("consent_revoked", actor, identity_id,
                           f"Identidade #{identity_id}: consentimento revogado e cadastro apagado.")
            return self._public(self._row(identity_id), self.clock())

    def delete(self, identity_id, actor):
        with self.mutex:
            self._row(identity_id)
            with self.db:
                self.db.execute("DELETE FROM face_templates WHERE identity_id=?", (identity_id,))
                self.db.execute("DELETE FROM identities WHERE id=?", (identity_id,))
                self.audit("identity_deleted", actor, identity_id,
                           f"Identidade #{identity_id} excluída: apelido, consentimento, "
                           "cadastro e horários foram removidos.")

    def enroll_face(self, identity_id, vectors, model, actor):
        """Guarda os vetores faciais (cifrados), substituindo os anteriores. Sem imagens."""
        with self.mutex:
            self.purge_expired()
            row = self._row(identity_id)
            if self.vault is None or not self.vault.available:
                raise HTTPException(503, "O cofre de vetores faciais não está disponível.")
            if row["consent_revoked_at"] is not None:
                raise HTTPException(409, "O consentimento foi revogado; não é possível cadastrar.")
            if row["consent_version"] != CONSENT_VERSION:
                raise HTTPException(
                    409, "Esta identidade aceitou um termo antigo, que não cobre o vetor facial. "
                         "Exclua-a e cadastre de novo com o termo atual.",
                )
            now = self.clock()
            sealed = [(identity_id, self.vault.seal(identity_id, vector), model, now)
                      for vector in vectors]
            with self.db:
                self.db.execute("DELETE FROM face_templates WHERE identity_id=?", (identity_id,))
                self.db.executemany(
                    "INSERT INTO face_templates(identity_id,sealed,model,created_at) "
                    "VALUES (?,?,?,?)", sealed,
                )
                self.db.execute(
                    "UPDATE identities SET face_samples=?, enrolled_at=? WHERE id=?",
                    (len(sealed), now, identity_id),
                )
                self.audit("face_enrolled", actor, identity_id,
                           f"Identidade #{identity_id}: cadastro facial registrado com "
                           f"{len(sealed)} amostras. Nenhuma imagem foi armazenada; somente "
                           "vetores cifrados.")
            return self._public(self._row(identity_id), now)

    def face_candidates(self, exclude=None):
        """Vetores de todas as identidades com cadastro facial e consentimento vigente."""
        with self.mutex:
            self.purge_expired()
            if self.vault is None or not self.vault.available:
                return {}
            rows = self.db.execute(
                "SELECT t.identity_id, t.sealed FROM face_templates t "
                "JOIN identities i ON i.id=t.identity_id WHERE i.consent_revoked_at IS NULL "
                "ORDER BY t.identity_id, t.id",
            ).fetchall()
            found: dict[int, list] = {}
            for row in rows:
                if row["identity_id"] == exclude:
                    continue
                try:
                    vector = self.vault.open(row["identity_id"], row["sealed"])
                except ValueError:
                    continue  # chave trocada ou dado adulterado: este vetor não serve
                found.setdefault(row["identity_id"], []).append(vector)
            return found

    def decide(self, identity_id) -> Decision:
        """Consulta a autorização atual. Uma identidade vencida já foi excluída (404)."""
        with self.mutex:
            self.purge_expired()
            return evaluate(self._row(identity_id), self.clock())

    def events(self):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM identity_events ORDER BY id DESC LIMIT 50",
        )]
