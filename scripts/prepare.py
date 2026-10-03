"""Prepara somente o ambiente virtual do projeto, quando as dependências mudam."""

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_models() -> None:
    """Baixa os modelos do reconhecimento facial na primeira vez. Falhar não impede o app."""
    script = ROOT / "scripts" / "baixar_modelos.py"
    try:
        failed = subprocess.run([sys.executable, str(script), "--silencioso"], cwd=ROOT,
                                check=False).returncode != 0
    except OSError:
        failed = True
    if failed:
        print("Aviso: os modelos do reconhecimento facial não foram baixados (veja acima). O "
              "restante do EverLock funciona; para tentar de novo, rode\n"
              "  .venv\\Scripts\\python scripts\\baixar_modelos.py", flush=True)


def main() -> None:
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Execute este preparador com o Python da pasta .venv.")
    fingerprint = hashlib.sha256(
        (ROOT / "requirements.lock.txt").read_bytes() + (ROOT / "pyproject.toml").read_bytes()
        + str(ROOT).encode() + sys.version.encode()
    ).hexdigest()
    marker = Path(sys.prefix) / ".everlock-ready"
    if marker.exists() and marker.read_text() == fingerprint:
        ensure_models()
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
    ensure_models()


if __name__ == "__main__":
    main()
