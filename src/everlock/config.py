"""Leitura do arquivo local everlock.env (variáveis EVERLOCK_*), sem sobrescrever o ambiente."""

import os
from pathlib import Path


def load_env_file(path: Path) -> bool:
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key.startswith("EVERLOCK_") and value:
            os.environ.setdefault(key, value)
    return True
