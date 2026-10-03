import argparse
import getpass
import os
import sys
from pathlib import Path

import uvicorn

from everlock.app import PROJECT_DIR
from everlock.backup import BackupError, create_backup, restore_backup
from everlock.config import load_env_file
from everlock.mailer import Mailer


def data_dir() -> Path:
    return Path(os.getenv("EVERLOCK_DATA_DIR", str(PROJECT_DIR / "data"))).resolve()


def ask_passphrase(confirm: bool) -> str:
    passphrase = getpass.getpass("Senha da cópia de segurança: ")
    if confirm and passphrase != getpass.getpass("Repita a senha: "):
        raise BackupError("As senhas não conferem.")
    return passphrase


def run_backup(args) -> None:
    out_dir = Path(args.pasta) if args.pasta else PROJECT_DIR / "backups"
    path = create_backup(data_dir(), out_dir, ask_passphrase(True) if args.senha else None)
    print(f"Cópia criada: {path}")
    if not args.senha:
        print("ATENÇÃO: esta cópia NÃO tem senha e contém o banco e a chave dos rostos. Guarde-a "
              "em lugar protegido ou refaça com --senha.")


def run_restore(args) -> None:
    passphrase = ask_passphrase(False) if args.senha else None
    names = restore_backup(Path(args.arquivo), data_dir(), passphrase, args.forcar)
    print(f"Restaurado em {data_dir()}: {', '.join(names)}. Inicie o EverLock normalmente.")


def serve() -> None:
    port = int(os.getenv("EVERLOCK_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("EVERLOCK_PORT deve estar entre 1 e 65535.")
    print(f"EverLock • simulador local: http://127.0.0.1:{port}", flush=True)
    print("E-mail de confirmação: " + (
        "configurado." if Mailer.from_environment().configured
        else "NÃO configurado; os links aparecerão neste terminal (veja everlock.env.example)."
    ), flush=True)
    uvicorn.run(
        "everlock.app:create_app", factory=True, host="127.0.0.1", port=port, access_log=False,
    )


def main(argv: list[str] | None = None) -> None:
    load_env_file(Path.cwd() / "everlock.env")
    parser = argparse.ArgumentParser(prog="everlock", description="Simulador local EverLock.")
    commands = parser.add_subparsers(dest="command")
    backup = commands.add_parser("backup", help="cria uma cópia de segurança (banco + chave)")
    backup.add_argument("--pasta", help="onde salvar (padrão: pasta backups do projeto)")
    backup.add_argument("--senha", action="store_true", help="protege a cópia com senha")
    restore = commands.add_parser("restaurar", help="restaura uma cópia (pare o EverLock antes)")
    restore.add_argument("arquivo", help="arquivo .zip ou .elbak")
    restore.add_argument("--senha", action="store_true", help="a cópia tem senha")
    restore.add_argument("--forcar", action="store_true", help="substitui os dados atuais")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            run_backup(args)
        elif args.command == "restaurar":
            run_restore(args)
        else:
            serve()
    except BackupError as error:
        sys.exit(f"Erro: {error}")


if __name__ == "__main__":
    main()
