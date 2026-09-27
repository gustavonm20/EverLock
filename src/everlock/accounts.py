"""Contas locais; o tempo de sessão nunca usa o relógio da simulação."""

import hashlib
import hmac
import secrets
import sqlite3
import time
import unicodedata
from datetime import UTC, datetime

from fastapi import HTTPException

SESSION_SECONDS = 8 * 3600
PASSWORD_RULE = (
    "Use pelo menos 6 caracteres, com letra maiúscula, minúscula, "
    "número e caractere especial (como . ? @ $). Não há limite máximo."
)


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
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(users)")}
        if "pending" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE users ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")

    def audit(self, kind, actor, detail):
        self.db.execute(
            "INSERT INTO account_events(type,actor,detail,created_at) VALUES (?,?,?,?)",
            (kind, actor, detail, datetime.now(UTC).isoformat()),
        )

    def needs_setup(self):
        return self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None

    def setup(self, username, password):
        with self.mutex:
            if not self.needs_setup():
                raise HTTPException(409, "O administrador inicial já foi configurado.")
            with self.db:
                self.db.execute("INSERT INTO users(username,password_hash,role) VALUES (?,?,?)",
                                (username, password_hash(password), "admin"))
                self.audit("setup", username, "Administrador inicial criado localmente.")

    def login(self, username, password, client):
        with self.mutex:
            now = self.clock()
            with self.db:
                self.db.execute("DELETE FROM login_attempts WHERE attempted_at <= ?", (now - 300,))
            limits = self.db.execute(
                "SELECT SUM(account=?), SUM(client=?) FROM login_attempts", (username, client),
            ).fetchone()
            if (limits[0] or 0) >= 5 or (limits[1] or 0) >= 20:
                raise HTTPException(429, "Muitas tentativas. Aguarde até cinco minutos.",
                                    headers={"Retry-After": "300"})
            row = self.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
            if not valid or row is None or not row["active"]:
                with self.db:
                    self.db.execute("INSERT INTO login_attempts VALUES (?,?,?)",
                                    (username, client, now))
                    self.audit("login_denied", None, "Tentativa de entrada recusada.")
                raise HTTPException(401, "Usuário ou senha inválidos.")
            token = secrets.token_urlsafe(32)
            with self.db:
                self.db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
                # Um login novo encerra a sessão anterior dessa conta.
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
                self.db.execute("INSERT INTO sessions VALUES (?,?,?)",
                                (token_hash(token), row["id"], now + SESSION_SECONDS))
                self.db.execute("DELETE FROM login_attempts WHERE account=?", (username,))
                self.audit("login", username, "Sessão iniciada por até oito horas reais.")
            return token

    def current(self, token):
        if not token or len(token) > 128:
            return None
        row = self.db.execute(
            """SELECT u.id, u.username, u.role, u.active FROM sessions s
               JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
            (token_hash(token), self.clock()),
        ).fetchone()
        return dict(row) if row else None

    def require(self, token, admin=False):
        user = self.current(token)
        if user is None:
            raise HTTPException(401, "Entre na sua conta para continuar.")
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
            "SELECT id,username,role,active,pending FROM users ORDER BY pending DESC,username",
        )]

    def register(self, username, password, client):
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
            self.create(username, password, "user", None, pending=True)

    def create(self, username, password, role, actor, pending=False):
        if self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 100:
            raise HTTPException(409, "O laboratório suporta até 100 contas.")
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO users(username,password_hash,role,active,pending) "
                    "VALUES (?,?,?,?,?)",
                    (username, password_hash(password), role, not pending, pending),
                )
                if pending:
                    self.audit("registration_requested", None,
                               f"Conta {username} aguarda aprovação de administrador.")
                else:
                    self.audit("user_created", actor, f"Conta {username} criada como {role}.")
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "Esse nome de usuário já está em uso.") from error

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
