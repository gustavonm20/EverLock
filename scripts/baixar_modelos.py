"""Baixa os dois modelos de reconhecimento facial do OpenCV (YuNet e SFace) para data/models.

Os arquivos são conferidos por tamanho e SHA-256 fixos: um arquivo trocado ou corrompido é
recusado e apagado. Os modelos são livres (licença Apache 2.0 / MIT) e ficam só neste computador.
Execute uma vez:  .venv\\Scripts\\python scripts\\baixar_modelos.py
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from everlock.config import load_env_file  # noqa: E402

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models/"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        BASE + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        232_589, "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        BASE + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        38_696_353, "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def checked(path: Path, size: int, digest: str) -> bool:
    return (path.is_file() and path.stat().st_size == size
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest)


def main() -> int:
    quiet = "--silencioso" in sys.argv
    load_env_file(ROOT / "everlock.env")
    target = Path(os.getenv("EVERLOCK_DATA_DIR", str(ROOT / "data"))) / "models"
    target.mkdir(parents=True, exist_ok=True)
    for name, (url, size, digest) in MODELS.items():
        path = target / name
        if checked(path, size, digest):
            if not quiet:
                print(f"OK   {name} (já baixado e verificado)")
            continue
        print(f"Baixando {name} ({size / 1_000_000:.1f} MB), só na primeira vez...", flush=True)
        partial = path.with_suffix(".parcial")
        try:
            with urllib.request.urlopen(url, timeout=60) as reply, partial.open("wb") as out:
                while chunk := reply.read(1 << 20):
                    out.write(chunk)
        except OSError as error:
            partial.unlink(missing_ok=True)
            print(f"ERRO ao baixar {name}: {error}\nConfira a internet e tente de novo.")
            return 1
        if not checked(partial, size, digest):
            partial.unlink(missing_ok=True)
            print(f"ERRO: {name} não confere com o tamanho/SHA-256 esperado. Arquivo apagado.")
            return 1
        partial.replace(path)
        print(f"OK   {name} verificado")
    if not quiet or any(not checked(target / n, s, d) for n, (_, s, d) in MODELS.items()):
        print(f"\nModelos prontos em {target}. Reinicie o EverLock.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
