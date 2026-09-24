"""Prepara somente o ambiente virtual do projeto, quando as dependências mudam."""

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Execute este preparador com o Python da pasta .venv.")
    fingerprint = hashlib.sha256(
        (ROOT / "requirements.lock.txt").read_bytes() + (ROOT / "pyproject.toml").read_bytes()
        + str(ROOT).encode() + sys.version.encode()
    ).hexdigest()
    marker = Path(sys.prefix) / ".everlock-ready"
    if marker.exists() and marker.read_text() == fingerprint:
        return
    if importlib.util.find_spec("pip") is None:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=True)
    print("Preparando bibliotecas gratuitas do EverLock...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.lock.txt")],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(ROOT),
         "--no-deps", "--no-build-isolation"],
        cwd=ROOT, check=True,
    )
    marker.write_text(fingerprint)


if __name__ == "__main__":
    main()
