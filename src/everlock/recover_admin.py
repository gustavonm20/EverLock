"""Recuperação local: execute com o servidor encerrado e acesso ao banco."""

import getpass
import os
import sys
from pathlib import Path
from threading import RLock

from everlock.accounts import PASSWORD_RULE, Accounts, password_hash, validate_password
from everlock.storage import Storage


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m everlock.recover_admin nome_do_administrador")
    default = Path(__file__).resolve().parents[2] / "data"
    path = Path(os.getenv("EVERLOCK_DATA_DIR", str(default))) / "everlock.sqlite3"
    if not path.is_file():
        raise SystemExit("Banco não encontrado. Confira EVERLOCK_DATA_DIR.")
    storage = Storage(path)
    try:
        accounts = Accounts(storage.connection, RLock())
        username = sys.argv[1].lower()
        row = accounts.db.execute(
            "SELECT id FROM users WHERE username=? AND role='admin' AND active=1", (username,),
        ).fetchone()
        if row is None:
            raise SystemExit("Administrador ativo não encontrado.")
        print(PASSWORD_RULE)
        password = getpass.getpass("Nova senha: ")
        try:
            validate_password(password)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        if password != getpass.getpass("Repita a nova senha: "):
            raise SystemExit("As senhas não conferem.")
        with accounts.db:
            accounts.db.execute("UPDATE users SET password_hash=? WHERE id=?",
                                (password_hash(password), row[0]))
            accounts.db.execute("DELETE FROM sessions WHERE user_id=?", (row[0],))
            accounts.audit("admin_recovered", "console_local",
                           f"Senha de {username} recuperada; sessões revogadas.")
        print("Senha atualizada. Inicie o EverLock e entre novamente.")
    finally:
        storage.close()


if __name__ == "__main__":
    main()
