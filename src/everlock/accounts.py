"""Contas locais; o tempo de sessão nunca usa o relógio da simulação."""

import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from datetime import UTC, datetime
from typing import NamedTuple

from fastapi import HTTPException

SESSION_SECONDS = 8 * 3600
CONFIRMATION_SECONDS = 24 * 3600
RESET_SECONDS = 3600
RESET_REQUEST_LIMIT = 5
INVITE_SECONDS = 24 * 3600
MAX_OPEN_INVITES = 10
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sem 0/O, 1/I/L: fácil de ditar
_EMAIL = re.compile(
    r"^[a-z0-9._%+\-]{1,64}@[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)*\.[a-z]{2,24}$"
)
PASSWORD_RULE = (
    "Use pelo menos 6 caracteres, com letra maiúscula, minúscula, "
    "número e caractere especial (como . ? @ $). Não há limite máximo."
)


def normalize_email(value: str) -> str:
    """Valida o formato e devolve o e-mail em minúsculas. A entrega é provada pela confirmação."""
    email = value.strip().lower()
    if len(email) > 254 or ".." in email or not _EMAIL.match(email):
        raise ValueError("Informe um e-mail válido, como nome@exemplo.com.")
    return email


def normalize_invite(code: str) -> str:
    """Aceita o código com ou sem hífens, espaços e em qualquer caixa."""
    return "".join(char for char in code.upper() if char.isalnum())


class Registered(NamedTuple):
    user_id: int
    token: str


def validate_password(password: str) -> str:
    if not (
        len(password) >= 6
        and any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(c.isdecimal() for c in password)
        and any(unicodedata.category(c)[0] in {"P", "S"} for c in password)
    ):
        raise ValueError(PASSWORD_RULE)
    return password


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                           n=2**15, r=8, p=3, maxmem=64 * 1024 * 1024).hex()
    return f"scrypt$32768$8$3${salt}${value}"


def password_matches(password: str, stored: str) -> bool:
    try:
        prefix, n, r, p, salt, _ = stored.split("$")
        if (prefix, n, r, p) != ("scrypt", "32768", "8", "3"):
            return False
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, connection, mutex, clock=time.time):
        self.db, self.mutex, self.clock = connection, mutex, clock
        self.notifier = None  # a aplicação liga
        self.dummy_hash = password_hash(secrets.token_urlsafe(24))
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                account TEXT NOT NULL, client TEXT NOT NULL, attempted_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_events (
                id INTEGER PRIMARY KEY, type TEXT NOT NULL, actor TEXT,
                detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS registration_attempts (
                client TEXT NOT NULL, attempted_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reset_attempts (
                client TEXT NOT NULL, attempted_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sealed BLOB NOT NULL,
                model TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS account_face_owner ON account_faces(user_id);
            CREATE TABLE IF NOT EXISTS admin_invites (
                id INTEGER PRIMARY KEY,
                code_hash TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                used_by INTEGER,
                used_at REAL
            );
            CREATE TABLE IF NOT EXISTS email_confirmations (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(users)")}
        if "pending" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE users ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
        # Contas anteriores não têm e-mail e continuam entrando pelo nome de usuário.
        if "email" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "email_confirmed" not in columns:
            with self.db:
                self.db.execute(
                    "ALTER TABLE users ADD COLUMN email_confirmed INTEGER NOT NULL DEFAULT 1"
                )
        session_columns = {row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        if "method" not in session_columns:
            with self.db:
                self.db.execute(
                    "ALTER TABLE sessions ADD COLUMN method TEXT NOT NULL DEFAULT 'password'"
                )
        for column, definition in (("face_samples", "INTEGER NOT NULL DEFAULT 0"),
                                   ("face_enrolled_at", "REAL"),
                                   ("face_consent_version", "TEXT")):
            if column not in columns:
                with self.db:
                    self.db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        with self.db:
            self.db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS user_email ON users(email) "
                "WHERE email IS NOT NULL"
            )

    def audit(self, kind, actor, detail):
        self.db.execute(
            "INSERT INTO account_events(type,actor,detail,created_at) VALUES (?,?,?,?)",
            (kind, actor, detail, datetime.now(UTC).isoformat()),
        )
        if self.notifier is not None:
            self.notifier.publish(kind, f"Conta: {kind}", detail, "accounts", "info", actor)

    def needs_setup(self):
        return self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None

    def setup(self, username, email, password):
        with self.mutex:
            if not self.needs_setup():
                raise HTTPException(409, "O administrador inicial já foi configurado.")
            with self.db:
                self.db.execute(
                    "INSERT INTO users(username,email,password_hash,role) VALUES (?,?,?,?)",
                    (username, email, password_hash(password), "admin"),
                )
                self.audit("setup", username, "Administrador inicial criado localmente.")

    def _authenticate(self, identifier, password, client):
        """Confere e-mail ou usuário e senha, com limite de tentativas. Exige a trava."""
        now = self.clock()
        with self.db:
            self.db.execute("DELETE FROM login_attempts WHERE attempted_at <= ?", (now - 300,))
        limits = self.db.execute(
            "SELECT SUM(account=?), SUM(client=?) FROM login_attempts", (identifier, client),
        ).fetchone()
        if (limits[0] or 0) >= 5 or (limits[1] or 0) >= 20:
            raise HTTPException(429, "Muitas tentativas. Aguarde até cinco minutos.",
                                headers={"Retry-After": "300"})
        # Usuário não contém "@", então um identificador nunca casa com duas contas.
        row = self.db.execute(
            "SELECT * FROM users WHERE username=? OR email=?", (identifier, identifier),
        ).fetchone()
        valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
        if not valid or row is None or not row["active"]:
            with self.db:
                self.db.execute("INSERT INTO login_attempts VALUES (?,?,?)",
                                (identifier, client, now))
                self.audit("login_denied", None, "Tentativa de entrada recusada.")
            raise HTTPException(401, "E-mail, usuário ou senha inválidos.")
        return row

    def login(self, identifier, password, client):
        with self.mutex:
            row = self._authenticate(identifier, password, client)
            if not row["email_confirmed"]:
                with self.db:
                    self.audit("login_unconfirmed", row["username"],
                               "Entrada bloqueada: e-mail ainda não confirmado.")
                raise HTTPException(403, detail={
                    "code": "email_unconfirmed",
                    "message": "Confirme seu e-mail para entrar. Abra o link que enviamos "
                               "ou peça um novo e-mail.",
                })
            with self.db:
                self.db.execute("DELETE FROM login_attempts WHERE account=?", (identifier,))
                return self._start_session(row, "login",
                                           "Sessão iniciada por até oito horas reais.")

    def _start_session(self, row, kind, detail) -> str:
        """Abre a sessão da conta (a anterior é encerrada). Chamar dentro de `with self.db`."""
        now, token = self.clock(), secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        self.db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        method = "face" if kind == "login_face" else "password"
        self.db.execute(
            "INSERT INTO sessions(token_hash,user_id,expires_at,method) VALUES (?,?,?,?)",
            (token_hash(token), row["id"], now + SESSION_SECONDS, method),
        )
        self.audit(kind, row["username"], detail)
        return token

    def confirm_password(self, username, password, client):
        """Pede a senha de novo antes de ações sensíveis de quem já está logado."""
        with self.mutex:
            try:
                self._authenticate(username, password, client)
            except HTTPException as error:
                if error.status_code == 401:
                    raise HTTPException(403, "Senha incorreta.") from error
                raise

    def record(self, kind, actor, detail):
        with self.mutex, self.db:
            self.audit(kind, actor, detail)

    # --- rosto da conta (login facial) ---------------------------------------------------

    def face_info(self, user_id):
        row = self.db.execute(
            "SELECT face_samples,face_enrolled_at,face_consent_version FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        return {"enrolled": bool(row["face_samples"]), "samples": row["face_samples"],
                "enrolled_at": row["face_enrolled_at"],
                "consent_version": row["face_consent_version"]}

    def save_face(self, user_id, username, sealed, model, consent_version):
        with self.mutex, self.db:
            now = self.clock()
            self.db.execute("DELETE FROM account_faces WHERE user_id=?", (user_id,))
            self.db.executemany(
                "INSERT INTO account_faces(user_id,sealed,model,created_at) VALUES (?,?,?,?)",
                [(user_id, item, model, now) for item in sealed],
            )
            self.db.execute(
                "UPDATE users SET face_samples=?, face_enrolled_at=?, face_consent_version=? "
                "WHERE id=?", (len(sealed), now, consent_version, user_id),
            )
            self.audit("face_enrolled", username,
                       f"Rosto da conta {username} cadastrado com {len(sealed)} amostras "
                       "(somente vetores cifrados; nenhuma imagem).")

    def remove_face(self, user_id, actor):
        with self.mutex, self.db:
            row = self.db.execute("SELECT username,face_samples FROM users WHERE id=?",
                                  (user_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Conta não encontrada.")
            if not row["face_samples"]:
                raise HTTPException(409, "Esta conta não tem rosto cadastrado.")
            self.db.execute("DELETE FROM account_faces WHERE user_id=?", (user_id,))
            self.db.execute("UPDATE users SET face_samples=0, face_enrolled_at=NULL, "
                            "face_consent_version=NULL WHERE id=?", (user_id,))
            self.audit("face_removed", actor, f"Rosto da conta {row['username']} removido.")

    def face_vectors(self, vault, exclude=None):
        """Vetores das contas que podem entrar pelo rosto: ativas, confirmadas e aprovadas."""
        if vault is None or not vault.available:
            return {}
        rows = self.db.execute(
            "SELECT f.user_id, f.sealed FROM account_faces f JOIN users u ON u.id=f.user_id "
            "WHERE u.active=1 AND u.pending=0 AND u.email_confirmed=1 ORDER BY f.user_id, f.id",
        ).fetchall()
        found: dict[int, list] = {}
        for row in rows:
            if row["user_id"] == exclude:
                continue
            try:
                found.setdefault(row["user_id"], []).append(
                    vault.open(row["user_id"], row["sealed"], "conta"))
            except ValueError:
                continue  # chave trocada ou dado adulterado: este vetor não serve
        return found

    def login_by_face(self, user_id) -> str:
        with self.mutex, self.db:
            row = self.db.execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)
                                  ).fetchone()
            if row is None:
                raise HTTPException(401, "Conta indisponível.")
            return self._start_session(row, "login_face",
                                       "Sessão iniciada pelo rosto, por até oito horas reais.")

    def current(self, token):
        if not token or len(token) > 128:
            return None
        row = self.db.execute(
            """SELECT u.id, u.username, u.role, u.active, s.method AS session_method FROM sessions s
               JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
            (token_hash(token), self.clock()),
        ).fetchone()
        return dict(row) if row else None

    def require(self, token, admin=False, password_session=False):
        """`password_session`: ações que não podem partir de uma sessão aberta só pelo rosto."""
        user = self.current(token)
        if user is None:
            raise HTTPException(401, "Entre na sua conta para continuar.")
        if password_session and user["session_method"] == "face":
            with self.db:
                self.audit("face_session_restricted", user["username"],
                           "Ação recusada: a sessão foi aberta pelo rosto, sem senha.")
            raise HTTPException(403, detail={
                "code": "password_required",
                "message": "Esta ação exige uma sessão aberta com senha, porque a atual foi "
                           "aberta pelo rosto. Saia e entre com e-mail ou usuário e senha.",
            })
        if admin and user["role"] != "admin":
            with self.db:
                self.audit("permission_denied", user["username"],
                           "Operação administrativa recusada.")
            raise HTTPException(403, "Esta ação exige uma conta de administrador.")
        return user

    def logout(self, token):
        with self.db:
            user = self.current(token)
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token or ""),))
            if user:
                self.audit("logout", user["username"], "Sessão encerrada.")

    def users(self):
        return [dict(row) for row in self.db.execute(
            "SELECT id,username,email,email_confirmed,role,active,pending,face_samples FROM users "
            "ORDER BY pending DESC,username",
        )]

    def _issue_token(self, user_id) -> str:
        token = secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM email_confirmations WHERE user_id=?", (user_id,))
        self.db.execute("INSERT INTO email_confirmations VALUES (?,?,?)",
                        (token_hash(token), user_id, self.clock() + CONFIRMATION_SECONDS))
        return token

    def register(self, username, email, password, client, role="user",
                 invite_code=None) -> Registered:
        """Cria a conta na hora, ainda sem poder entrar até confirmar o e-mail.

        Conta de administrador só nasce com um código de convite válido, gerado por outro
        administrador; sem ele, o papel escolhido nunca é concedido.
        """
        with self.mutex:
            if self.needs_setup():
                raise HTTPException(409, "Configure o administrador antes de abrir os cadastros.")
            now = self.clock()
            with self.db:
                self.db.execute("DELETE FROM registration_attempts WHERE attempted_at <= ?",
                                (now - 300,))
            total = self.db.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE client=?", (client,),
            ).fetchone()[0]
            if total >= 5:
                raise HTTPException(429, "Muitos cadastros. Aguarde até cinco minutos.",
                                    headers={"Retry-After": "300"})
            with self.db:
                self.db.execute("INSERT INTO registration_attempts VALUES (?,?)", (client, now))
            invite = None
            if role == "admin":
                invite = self.db.execute(
                    "SELECT id FROM admin_invites WHERE code_hash=? AND used_by IS NULL "
                    "AND expires_at>?", (token_hash(normalize_invite(invite_code or "")), now),
                ).fetchone()
                if invite is None:
                    with self.db:
                        self.audit("invite_rejected", None,
                                   f"Cadastro de administrador recusado para {username}: "
                                   "código de convite inválido, expirado ou já usado.")
                    raise HTTPException(403, "Código de convite inválido, expirado ou já usado.")
            with self.db:
                user_id = self._insert(username, email, password, role, confirmed=False)
                if invite is not None:
                    self.db.execute("UPDATE admin_invites SET used_by=?, used_at=? WHERE id=?",
                                    (user_id, now, invite["id"]))
                token = self._issue_token(user_id)
                self.audit("registration_created", None,
                           f"Conta {username} criada como {role}"
                           f"{' com convite de administrador' if invite else ''}; "
                           "aguarda a confirmação do e-mail.")
            return Registered(user_id, token)

    def discard_unconfirmed(self, user_id):
        """Desfaz um cadastro cujo e-mail não pôde ser enviado, liberando usuário e e-mail."""
        with self.mutex, self.db:
            row = self.db.execute(
                "SELECT username FROM users WHERE id=? AND email_confirmed=0", (user_id,),
            ).fetchone()
            if row is None:
                return
            self.db.execute("DELETE FROM email_confirmations WHERE user_id=?", (user_id,))
            # O convite volta a valer: o cadastro que o consumiu foi desfeito.
            self.db.execute("UPDATE admin_invites SET used_by=NULL, used_at=NULL WHERE used_by=?",
                            (user_id,))
            self.db.execute("DELETE FROM users WHERE id=?", (user_id,))
            self.audit("registration_cancelled", None,
                       f"Cadastro de {row['username']} desfeito: o e-mail não pôde ser enviado.")

    def confirm_email(self, token):
        with self.mutex:
            now = self.clock()
            with self.db:
                self.db.execute("DELETE FROM email_confirmations WHERE expires_at <= ?", (now,))
            row = self.db.execute(
                "SELECT c.user_id, u.username FROM email_confirmations c "
                "JOIN users u ON u.id=c.user_id WHERE c.token_hash=?", (token_hash(token),),
            ).fetchone()
            if row is None:
                raise HTTPException(400, "Link inválido ou expirado. Tente entrar com a sua "
                                         "conta para receber um novo e-mail.")
            with self.db:
                user_id = row["user_id"]
                self.db.execute("UPDATE users SET email_confirmed=1 WHERE id=?", (user_id,))
                self.db.execute("DELETE FROM email_confirmations WHERE user_id=?", (user_id,))
                self.audit("email_confirmed", row["username"], "E-mail confirmado.")

    def resend_confirmation(self, identifier, password, client):
        """Novo link para quem prova ser dono da conta (senha correta). Devolve e-mail e token."""
        with self.mutex:
            row = self._authenticate(identifier, password, client)
            if row["email_confirmed"] or row["email"] is None:
                raise HTTPException(409, "Este e-mail já foi confirmado. Entre normalmente.")
            with self.db:
                token = self._issue_token(row["id"])
                self.audit("confirmation_resent", row["username"], "Novo link de confirmação.")
            return row["email"], row["username"], token

    def _insert(self, username, email, password, role, confirmed) -> int:
        if self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 100:
            raise HTTPException(409, "O laboratório suporta até 100 contas.")
        if self.db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, "Esse nome de usuário já está em uso.")
        if self.db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "Esse e-mail já está cadastrado.")
        cursor = self.db.execute(
            "INSERT INTO users(username,email,email_confirmed,password_hash,role) "
            "VALUES (?,?,?,?,?)",
            (username, email, int(confirmed), password_hash(password), role),
        )
        return cursor.lastrowid

    def create(self, username, email, password, role, actor):
        """Conta criada por um administrador: ele responde pelo e-mail, sem confirmação."""
        with self.db:
            self._insert(username, email, password, role, confirmed=True)
            self.audit("user_created", actor, f"Conta {username} criada como {role}.")

    def create_invite(self, actor):
        """Gera um código de uso único. Ele só é mostrado agora; o banco guarda o hash."""
        with self.mutex:
            now = self.clock()
            open_count = self.db.execute(
                "SELECT COUNT(*) FROM admin_invites WHERE used_by IS NULL AND expires_at>?", (now,),
            ).fetchone()[0]
            if open_count >= MAX_OPEN_INVITES:
                raise HTTPException(409, f"Já existem {MAX_OPEN_INVITES} convites abertos. "
                                         "Revogue algum antes de criar outro.")
            raw = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(12))
            with self.db:
                cursor = self.db.execute(
                    "INSERT INTO admin_invites(code_hash,created_by,created_at,expires_at) "
                    "VALUES (?,?,?,?)", (token_hash(raw), actor, now, now + INVITE_SECONDS),
                )
                self.audit("invite_created", actor,
                           f"Convite #{cursor.lastrowid} de administrador criado; vale 24 horas.")
            code = "-".join(raw[i:i + 4] for i in range(0, 12, 4))
            return {"id": cursor.lastrowid, "code": code, "expires_at": now + INVITE_SECONDS}

    def invites(self):
        return [dict(row) for row in self.db.execute(
            "SELECT id,created_by,created_at,expires_at FROM admin_invites "
            "WHERE used_by IS NULL AND expires_at>? ORDER BY id", (self.clock(),),
        )]

    def revoke_invite(self, invite_id, actor):
        with self.mutex, self.db:
            deleted = self.db.execute(
                "DELETE FROM admin_invites WHERE id=? AND used_by IS NULL", (invite_id,),
            ).rowcount
            if not deleted:
                raise HTTPException(404, "Convite não encontrado ou já usado.")
            self.audit("invite_revoked", actor, f"Convite #{invite_id} revogado.")

    def update(self, user_id, role, active, actor):
        row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Conta não encontrada.")
        if row["role"] == "admin" and row["active"] and (role != "admin" or not active):
            total = self.db.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1",
            ).fetchone()[0]
            if total <= 1:
                raise HTTPException(409, "Mantenha pelo menos um administrador ativo.")
        with self.db:
            self.db.execute("UPDATE users SET role=?,active=?,pending=0 WHERE id=?",
                            (role, active, user_id))
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            self.audit("user_updated", actor,
                       f"Conta {row['username']}: papel {role}, ativa={bool(active)}. "
                       "Sessões revogadas.")

    def request_password_reset(self, identifier, client):
        """Prepara a redefinição. Devolve (e-mail, usuário, token) ou None se não houver conta
        apta. Quem chama responde sempre igual, para não revelar quais contas existem."""
        with self.mutex:
            now = self.clock()
            with self.db:
                self.db.execute("DELETE FROM reset_attempts WHERE attempted_at <= ?", (now - 300,))
            recent = self.db.execute("SELECT COUNT(*) FROM reset_attempts WHERE client=?",
                                     (client,)).fetchone()[0]
            if recent >= RESET_REQUEST_LIMIT:
                raise HTTPException(429, "Muitos pedidos. Aguarde até cinco minutos.",
                                    headers={"Retry-After": "300"})
            with self.db:
                self.db.execute("INSERT INTO reset_attempts VALUES (?,?)", (client, now))
            row = self.db.execute(
                "SELECT id,username,email FROM users WHERE (username=? OR email=?) AND active=1 "
                "AND pending=0 AND email_confirmed=1 AND email IS NOT NULL",
                (identifier, identifier),
            ).fetchone()
            if row is None:
                return None
            token = secrets.token_urlsafe(32)
            with self.db:
                self.db.execute("DELETE FROM password_resets WHERE user_id=?", (row["id"],))
                self.db.execute("INSERT INTO password_resets VALUES (?,?,?)",
                                (token_hash(token), row["id"], now + RESET_SECONDS))
                self.audit("password_reset_requested", row["username"],
                           "Link de redefinição de senha gerado (vale 1 hora).")
            return row["email"], row["username"], token

    def reset_password(self, token, new_password):
        """Troca a senha com o link do e-mail: uso único, encerra todas as sessões."""
        with self.mutex:
            now = self.clock()
            with self.db:
                self.db.execute("DELETE FROM password_resets WHERE expires_at <= ?", (now,))
            row = self.db.execute(
                "SELECT r.user_id, u.username, u.email FROM password_resets r "
                "JOIN users u ON u.id=r.user_id WHERE r.token_hash=? AND u.active=1",
                (token_hash(token),),
            ).fetchone()
            if row is None:
                raise HTTPException(400, "Link inválido ou expirado. Peça um novo em “Esqueci "
                                         "minha senha”.")
            with self.db:
                self.db.execute("UPDATE users SET password_hash=? WHERE id=?",
                                (password_hash(new_password), row["user_id"]))
                self.db.execute("DELETE FROM password_resets WHERE user_id=?", (row["user_id"],))
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
                self.db.execute("DELETE FROM login_attempts WHERE account IN (?,?)",
                                (row["username"], row["email"]))
                self.audit("password_reset", row["username"],
                           "Senha redefinida pelo link do e-mail; sessões revogadas.")

    def change_password(self, user, old_password, new_password):
        row = self.db.execute(
            "SELECT password_hash FROM users WHERE id=?", (user["id"],),
        ).fetchone()
        if not password_matches(old_password, row[0]):
            raise HTTPException(403, "A senha atual não confere.")
        with self.db:
            self.db.execute("UPDATE users SET password_hash=? WHERE id=?",
                            (password_hash(new_password), user["id"]))
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            self.audit("password_changed", user["username"], "Senha alterada; sessões revogadas.")

    def events(self):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM account_events ORDER BY id DESC LIMIT 50",
        )]
