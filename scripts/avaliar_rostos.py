"""Avalia imagens autorizadas e distintas, sem abrir o app ou alterar seus limites.

Veja docs/avaliacao-facial.md antes de preparar o manifesto.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from everlock.evaluation import ManifestError, evaluate  # noqa: E402
from everlock.faces import FaceError, OpenCVFaceEngine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Manifesto JSON local com consentimento")
    parser.add_argument("--profile", choices=("door", "login"), default="door")
    parser.add_argument("--threshold", type=float, help="Limite experimental; não altera o app")
    parser.add_argument("--margin", type=float, help="Margem experimental; não altera o app")
    parser.add_argument("--models-dir", type=Path, default=(
        Path(os.getenv("EVERLOCK_DATA_DIR", str(ROOT / "data"))) / "models"))
    parser.add_argument("--output", type=Path,
                        help="Novo relatório .json; padrão: saída no terminal")
    args = parser.parse_args(argv)
    if args.output and args.output.suffix.lower() != ".json":
        parser.error("O relatório deve ter extensão .json.")
    try:
        engine = OpenCVFaceEngine(args.models_dir)
        report = evaluate(args.manifest, engine, profile=args.profile,
                          threshold=args.threshold, ambiguity_margin=args.margin)
        content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(content)
            print(f"Relatório salvo em {args.output}")
        else:
            print(content, end="")
        return 0 if report["gallery"]["subjects"] else 2
    except (ManifestError, FaceError, OSError, ValueError) as error:
        print(f"Avaliação não realizada: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
