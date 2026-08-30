#!/usr/bin/env python3
"""Build the Singapore-tuned CPU engine. Works on Windows, macOS and Linux.

Converts a Singlish-finetuned Whisper checkpoint to CTranslate2 so
`faster-whisper` can run it. This is the only Singapore-tuned option for
teammates who are not on Apple Silicon — MLX (and therefore Polyglot-Lion and
MERaLiON) is Mac-only, and generic whisper-small is the weakest choice for
Singlish.

    python scripts/convert_singlish.py

Then:  STT_ENGINE=singlish uvicorn stt.server:app

Deliberately Python rather than shell so Windows teammates can run it —
scripts/convert_polyglot_mlx.sh cannot be run on Windows at all.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Reported WER 9.69, finetuned on IMDA's National Speech Corpus. The mjwong
# checkpoints are reasonable alternatives if this one disappoints on your clips.
DEFAULT_MODEL = "jensenlwt/whisper-small-singlish-122k"
DEFAULT_OUT = REPO / "models" / "singlish-ct2"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--quantization", default="int8",
                    choices=["int8", "int8_float16", "float16", "float32"],
                    help="int8 is right for CPU; use float16 on a GPU")
    ap.add_argument("--force", action="store_true", help="overwrite existing output")
    args = ap.parse_args()

    # ctranslate2 publishes no wheels for 3.13 and no source dist, so the
    # install fails with a confusing pip error. Say so plainly instead.
    if sys.version_info >= (3, 13):
        print(f"ERROR: Python {sys.version_info.major}.{sys.version_info.minor} "
              "is not supported — ctranslate2 has no wheels for 3.13.\n"
              "       Use Python 3.12 or older:  py -3.12 -m venv .venv")
        return 2

    if args.output_dir.exists():
        if not args.force:
            print(f"{args.output_dir} already exists. Use --force to rebuild.")
            return 0
        shutil.rmtree(args.output_dir)

    converter = shutil.which("ct2-transformers-converter")
    cmd = (
        [converter] if converter
        else [sys.executable, "-m", "ctranslate2.converters.transformers"]
    )
    if not converter:
        try:
            import ctranslate2  # noqa: F401
        except ImportError:
            print("ERROR: ctranslate2 is not installed.\n"
                  "       pip install ctranslate2 transformers")
            return 2

    cmd += [
        "--model", args.model,
        "--output_dir", str(args.output_dir),
        "--quantization", args.quantization,
        "--copy_files", "tokenizer.json", "preprocessor_config.json",
    ]

    print(f"Converting {args.model}\n         -> {args.output_dir} ({args.quantization})")
    print("This downloads ~1GB and takes a few minutes.\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nConversion failed. The service still works without it — it "
              "falls back to generic whisper-small.")
        return result.returncode

    print("\nDone. Use it with:\n  STT_ENGINE=singlish python scripts/verify.py --record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
