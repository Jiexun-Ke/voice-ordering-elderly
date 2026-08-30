# STT service

Speech-to-text + order parsing for the voice ordering MVP. Runs as an HTTP
service so the frontend, backend and NLP work can proceed in parallel.

`voice_ordering.py` is **not** modified by any of this — its tuned parameters
were ported into `stt/engines/whisper.py` and its logic is left alone.

---

## Quick start

```bash
pip install -r requirements.txt

# Apple Silicon — primary engine
pip install mlx-qwen3-asr
./scripts/convert_polyglot_mlx.sh          # timebox to ~1h, see below

uvicorn stt.server:app --reload --host 0.0.0.0 --port 8000
```

### Windows / Linux / Intel Mac

MLX is Apple-Silicon-only, but you are **not** stuck with generic Whisper.
Build the Singapore-tuned CPU engine once:

```bash
pip install -r requirements.txt ctranslate2 transformers
python scripts/convert_singlish.py            # ~1GB download, a few minutes

STT_ENGINE=singlish uvicorn stt.server:app --host 0.0.0.0 --port 8000
```

**Python 3.12 or older is required.** `ctranslate2` publishes no wheels for
3.13 and no source distribution, so `pip install faster-whisper` simply fails
there. On Windows: `py -3.12 -m venv .venv`. No system ffmpeg is needed — audio
decoding goes through PyAV, which bundles it.

If you have an **NVIDIA GPU** (a gaming laptop counts), you can run the good
model instead:

```bash
pip install -U qwen-asr        # plus a CUDA-enabled torch
STT_ENGINE=polyglot-cuda uvicorn stt.server:app
```

Check any of these with: `curl localhost:8000/health` — look at `engine_ready`.

---

## API contract

Frozen on Day 1. Build against this before the model is finalised.

`POST /transcribe` — multipart upload, field name `audio`

| Query param | Default | Purpose |
|---|---|---|
| `catalogue` | `hawker` | Which merchant menu to use |
| `bias` | `true` | Set `false` to A/B whether catalogue biasing helps |

```json
{
  "text": "two kopi c siew dai tapao",
  "corrected_text": "two Kopi-C siew dai tapao",
  "matched_items": [
    {"term": "kopi c", "canonical": "KOPI_C", "display": "Kopi-C",
     "kind": "item", "score": 1.0}
  ],
  "order": {
    "lines": [{"canonical": "KOPI_C", "display": "Kopi-C", "quantity": 2,
               "modifiers": ["siew dai"], "price": 1.4}],
    "takeaway": true,
    "total": 2.8
  },
  "readback": "2x Kopi-C (siew dai) — takeaway",
  "confidence": -0.34,
  "low_confidence": false,
  "engine": "polyglot-lion-1.7b-mlx",
  "latency_ms": 310
}
```

**Backend team:** consume `order`. **Frontend team:** show `readback` for
confirmation, and re-ask when `low_confidence` is `true`.

Also: `GET /health`, `GET /catalogue?name=hawker`

---

## Choosing an engine

```bash
STT_ENGINE=polyglot      uvicorn stt.server:app   # default; Apple Silicon
STT_ENGINE=qwen          uvicorn stt.server:app   # base Qwen3-ASR — Cantonese/Minnan
STT_ENGINE=meralion      uvicorn stt.server:app   # MERaLiON-2-3B (pip install mlx-meralion)
STT_ENGINE=polyglot-cuda uvicorn stt.server:app   # NVIDIA GPU, any OS
STT_ENGINE=singlish      uvicorn stt.server:app   # CPU, any OS — Singapore-tuned
STT_ENGINE=whisper       uvicorn stt.server:app   # CPU, any OS — generic fallback
```

If the chosen engine's backend is not installed, the service logs a warning
and falls back to Whisper rather than failing to start. If *no* backend is
installed it still starts — so teammates on any machine can build against
`/catalogue` and the response contract — but `/health` reports
`"engine_ready": false` and `/transcribe` returns 503 with install
instructions. Trust `engine_ready`, not `engine`.

| Engine | Runs on | Notes |
|---|---|---|
| `polyglot` | Apple Silicon | Default. 14.85 avg error on SG's 4 languages. MIT. **No dialect training.** |
| `qwen` | Apple Silicon | Same code path, one model id. Advertises Cantonese + Minnan. |
| `meralion` | Apple Silicon | Claims Singlish/Hokkien/Cantonese. The quoted 14.32 belongs to the **10B**, not this 3B — measure it, don't assume. |
| `polyglot-cuda` | NVIDIA, any OS | Same model as `polyglot`, official `qwen-asr` runtime instead of MLX. |
| `singlish` | **CPU, any OS** | Singlish-finetuned Whisper (WER 9.69, IMDA corpus). Best non-Mac option. Needs `convert_singlish.py` first; falls back to `whisper` until then. |
| `whisper` | CPU, any OS | Generic fallback. Weaker on Singlish, but never blocks anyone. |

Every engine supports catalogue biasing, so switching costs nothing but a
model swap.

---

## Curating the catalogue — highest value, no coding

`data/catalogues/*.json`. Every item plus **every way an elderly diner might
say it**. This feeds two mechanisms at once: the biasing prompt sent to the
model *before* transcription, and the fuzzy matcher applied *after*. Improving
it improves both.

```json
{"canonical": "KOPI_C", "display": "Kopi-C", "price": 1.40,
 "aliases": ["kopi c", "kopi see", "kopi ci", "coffee with evaporated milk"]}
```

The biasing prompt is capped at ~200 tokens (longer prompts measurably hurt).
Display names are included first, so an over-long catalogue degrades by
dropping synonyms rather than whole products — but aliases still help the
fuzzy matcher even when they don't fit the prompt.

---

## Evaluation

```bash
python -m stt.eval data/eval --engines polyglot,qwen,whisper
```

Fill `data/eval/refs.csv` with `filename,reference,tag`. The `tag` column is
free-form; tagged rows (e.g. `dialect`, `elderly`) get their own column in the
output so you can see where an engine specifically fails.

```
engine                       bias       WER  WER+fix     p50     p95    n
------------------------------------------------------------------------
polyglot-lion-1.7b-mlx       on       0.000    0.000    310ms    310ms    4
whisper-small                on       0.200    0.000   1840ms   1840ms    4
```

`WER+fix` is after fuzzy correction — the number the backend actually sees,
and usually the more honest one.

Recorded `.wav` files are gitignored (they are large and contain people's
voices). To share a test set deliberately: `git add -f data/eval/*.wav`.

---

## Audio from the browser

Two supported routes:

1. **Upload 16 kHz mono WAV** (encode with the Web Audio API). No server
   dependency. Preferred.
2. **Upload the raw `MediaRecorder` blob** — Chrome gives WebM/Opus, Safari
   gives MP4/AAC. Needs `ffmpeg` on the server (`brew install ffmpeg`).
   `GET /health` reports whether ffmpeg was found.

Test on a **real iPhone**, not desktop Chrome. iOS `MediaRecorder` behaves
differently and it is a classic demo-day failure.

---

## Tests and verification

Two layers. The first runs anywhere; the second needs a real model, which is
why it is a script rather than a test.

```bash
python -m pytest tests/ -q          # 51 tests, no model or network needed
ruff check stt/ tests/ && mypy stt/ --ignore-missing-imports

python scripts/verify.py --record   # everything that needs a real model
```

`scripts/verify.py` records a clip from your mic, then checks: the engine
loads and warms up, **catalogue biasing is actually wired up**, a real
transcription succeeds and is fast enough, biasing measurably changes the
output, the port agrees with `voice_ordering.py`, and the live server returns
the full contract. Exit code 0 means everything passed, so it works in CI too.

Useful variants:

```bash
python scripts/verify.py --engine qwen --audio clip.wav
python scripts/verify.py --engine whisper        # tests the fallback path
```

The biasing check deserves particular attention: if the MLX wrapper exposes
its biasing parameter under a name this code does not recognise, biasing is
**silently disabled** — everything still appears to work while accuracy on
menu terms quietly rests on `correct.py` alone. `verify.py` turns that silent
failure into a loud one.

---

## Status — what is and isn't verified

**Verified** (51 passing tests on Linux/x86): catalogue loading and token
budget, fuzzy correction including unseen ASR corruptions, order parsing with
code-switched quantities, audio downmix/resample/guards, the full HTTP
contract, catalogue swapping, biasing on/off, engine fallback and
readiness reporting, and the eval harness.

**Not verified — needs a smoke test on Apple Silicon:** the MLX engines
(`polyglot`, `qwen`, `meralion`). They were written on an x86 Linux container
where MLX cannot install. In particular the biasing keyword is detected by
introspection at load time because the two MLX wrapper packages differ; if a
wrapper takes it under a different name, `stt/engines/mlx_qwen.py` logs a
warning and continues without biasing. **First thing to check on the Mac:**
that `/transcribe` logs no "exposes no biasing kwarg" warning.

The Whisper engine is also unexercised against a real model here (no download),
though its parameters are a direct port from the working prototype.
