"""Compara fotos de rostos com o mesmo motor do EverLock, sem abrir o aplicativo.

Serve para conferir se o OpenCV está funcionando e para calibrar o limite de reconhecimento:
  python scripts/testar_rosto.py pessoa_a_1.jpg pessoa_a_2.jpg pessoa_b_1.jpg
Mostra a similaridade (cosseno) de todos os pares e o giro de cada rosto (0 = de frente;
+ = virado para a esquerda da pessoa; - = para a direita). O login por rosto exige giro menor que
0,15 na foto de frente e maior que 0,22 (no lado pedido) na foto virada: tire uma foto de frente e
uma virada para conferir esses números na sua câmera. Fotos da MESMA pessoa devem ficar bem acima do
limite (padrão 0,45); fotos de pessoas DIFERENTES devem ficar bem abaixo. As imagens só são lidas
e nada é gravado. Use apenas fotos de quem autorizou.
"""

import itertools
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from everlock.biometrics import cosine  # noqa: E402
from everlock.faces import FaceError, OpenCVFaceEngine  # noqa: E402
from everlock.recognition import FaceSettings  # noqa: E402


def main(paths: list[str]) -> int:
    engine = OpenCVFaceEngine(Path(os.getenv("EVERLOCK_DATA_DIR", str(ROOT / "data"))) / "models")
    if not engine.available:
        print(f"Motor indisponível: {engine.reason}")
        return 1
    readings = {}
    for name in paths:
        try:
            readings[name] = engine.read(Path(name).read_bytes())
            reading = readings[name]
            print(f"{name}: rosto de {reading.face_pixels}px, nitidez {reading.sharpness:.0f}, "
                  f"giro {reading.yaw:+.2f}")
        except (FaceError, OSError) as error:
            print(f"{name}: recusada ({getattr(error, 'message', error)})")
    limit = FaceSettings().match_threshold
    for first, second in itertools.combinations(readings, 2):
        score = cosine(readings[first].embedding, readings[second].embedding)
        verdict = "mesma pessoa" if score >= limit else "pessoas diferentes"
        print(f"{first} x {second}: {score:.3f} -> {verdict} (limite {limit})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1:]))
