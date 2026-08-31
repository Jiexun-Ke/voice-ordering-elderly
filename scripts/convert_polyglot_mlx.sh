#!/usr/bin/env bash
# Convert Polyglot-Lion to MLX for Apple Silicon.
#
# TIMEBOX THIS TO ~1 HOUR (Day 1). The MLX packages document only the official
# Qwen/Qwen3-ASR-* checkpoints. Polyglot-Lion is the same architecture so this
# should work, but nobody has published doing it.
#
# If it fails, do NOT sink the day into it. Run the base model instead:
#     STT_ENGINE=qwen uvicorn stt.server:app
# It needs no conversion, shares the exact same code path, and advertises
# Cantonese and Minnan — which Polyglot-Lion does not.
set -euo pipefail

MODEL="${1:-knoveleng/polyglot-lion-1.7b}"
OUT="${2:-./models/polyglot-lion-mlx-8bit}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "MLX requires Apple Silicon. On other machines use: STT_ENGINE=whisper" >&2
  exit 1
fi

python -c "import mlx_qwen3_asr" 2>/dev/null || {
  echo "Installing mlx-qwen3-asr..." >&2
  pip install mlx-qwen3-asr
}

echo "Converting $MODEL -> $OUT (8-bit)"
# 8-bit is the quality-first profile (~3x faster than fp16); pass 4 for the
# speed-first profile if latency matters more than accuracy.
python -m mlx_qwen3_asr.convert \
  --model "$MODEL" --quantize 8 --group-size 64 --output-dir "$OUT" \
  || python scripts/convert.py \
       --model "$MODEL" --quantize 8 --group-size 64 --output-dir "$OUT"

echo
echo "Done. Point the service at it with:"
echo "  STT_ENGINE=polyglot STT_MODEL=$OUT uvicorn stt.server:app --port 8000"
