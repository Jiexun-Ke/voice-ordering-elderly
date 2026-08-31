# STT service

Speech-to-text + order parsing for the voice ordering MVP. Runs as an HTTP
service so the frontend, backend and NLP work can proceed in parallel.

`voice_ordering.py` is **not** modified by any of this — its tuned parameters
were ported into `stt/engines/whisper.py` and its logic is left alone.

---

## Quick start — same on every platform

The default engine is **`singlish`**: a Singapore-tuned Whisper on CTranslate2,
which runs on Windows, Linux, Intel Macs and Apple Silicon alike. Everyone on
the team gets identical behaviour, so a bug is never someone's platform.

```bash
pip install -r requirements.txt ctranslate2 transformers torch
python scripts/convert_singlish.py         # one-time, ~1GB

uvicorn stt.server:app --reload --host 0.0.0.0 --port 8000
```

**Python 3.10-3.12 is required.** Below 3.10 the MLX engines will not install;
3.13+ has no `ctranslate2` wheels. macOS ships 3.9, so install a newer one
alongside it rather than replacing it:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate
```

On Windows: `py -3.12 -m venv .venv`. No system ffmpeg needed — PyAV bundles it.

Everything works before you run the converter: the engine falls back to generic
`whisper-small` with a warning.

### Going faster on your own machine (optional)

```bash
# Apple Silicon — fastest and most accurate
pip install mlx-qwen3-asr && ./scripts/convert_polyglot_mlx.sh
STT_ENGINE=polyglot uvicorn stt.server:app

# NVIDIA GPU, any OS — same model, CUDA runtime
pip install -U qwen-asr
STT_ENGINE=polyglot-cuda uvicorn stt.server:app
```

Treat these as measurement options, not daily drivers. Day 4's bake-off decides
whether the demo ships on one of them; until then, uniform beats fast.

Check any of these with: `curl localhost:8000/health` — look at `engine_ready`.

---

## Where everything lives

The whole project is one folder. Copy it to another drive and it still works —
model weights included.

```
voice-ordering-elderly/
├── stt/                    the service
├── scripts/                setup and testing commands
├── data/
│   ├── catalogues/         merchant menus (edit these)
│   └── eval/               your recorded test clips + refs.csv
├── models/                 all downloaded weights (gitignored)
│   ├── singlish-ct2/       the converted engine
│   └── hf-cache/           HuggingFace downloads, pinned here not to ~/.cache
└── .venv/                  Python environment
```

**One caveat when you move drives:** `.venv` stores absolute paths internally,
so recreate it at the new location. Everything else moves as-is:

```bash
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt ctranslate2 transformers sounddevice
```

Weights in `models/` survive, so there is no second ~1GB download.

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

## Measured: why `singlish` is the default

Two clips of *"wo yao two kopi-c siew dai, da bao"* on an M4 Mac:

| Engine | Transcript | Parsed order |
|---|---|---|
| `singlish` | `Oh Yaw two Kopi C Siew Dai, Da Bao` | **2x Kopi-C (siew dai) — takeaway** all correct |
| `whisper` | `我要 do kopi siu dai, da bao.` | 1x Kopi (siew dai) — takeaway, two errors |

Plain Whisper made the same two mistakes on both clips: it heard "two" as
"do"/做 and collapsed the quantity to 1, and dropped the "C" so Kopi-C matched
plain Kopi. On the first clip it also hallucinated a trailing 蛋.

This contradicted the expectation going in. `singlish` is finetuned on a
Singapore *English* corpus, and finetuning Whisper on English-heavy data is
documented to damage multilingual ability, so it was expected to fail on
code-switched speech. Instead it **romanises** the Mandarin ("wo yao" ->
"Oh Yaw" / "Woyao" — inconsistently, but it is not a menu term so nothing
downstream cares) and every order field comes out right. Whisper wrote better
Chinese and produced a worse order.

Caveats: two clips from one speaker is indicative, not conclusive — the Day 3
test set is what settles it. And both engines take ~2.6s on CPU, which is a
noticeable wait for an elderly diner and the main argument for testing
`polyglot` on Apple Silicon.

Reproduce with:

```bash
python scripts/compare_engines.py --record --engines singlish,whisper
```

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
python -m pytest tests/ -q          # 52 tests, no model or network needed
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

**Verified on a real machine** (M4 Mac, Python 3.12): 63 tests pass, the
`singlish` engine transcribes real speech, and a spoken order becomes correct
structured JSON end to end. `ruff` and `mypy` are clean.

**Verified without a model** (any platform, no download): catalogue loading and
the biasing token budget, fuzzy correction including unseen ASR corruptions,
order parsing with code-switched quantities, audio downmix/resample/guards, the
full HTTP contract, catalogue swapping, biasing on/off, engine fallback and
readiness reporting, and the eval harness.

**Not yet run by anyone:** the MLX engines (`polyglot`, `qwen`, `meralion`) and
the CUDA engine (`polyglot-cuda`). They are written and behind the same
interface, but no one has executed them. First thing to check when you do: that
`/transcribe` logs no `"exposes no biasing kwarg"` warning — if it does,
catalogue biasing is silently off and accuracy rests on `correct.py` alone.

## What to do next

In priority order. The first is a hard gate on everything else.

### 1. Record the test set (nobody can skip this)

`data/eval/refs.csv` currently holds three placeholder rows. Until it holds real
recordings, **no question about which engine is better can be answered** — the
comparison below rests on two clips from one speaker, which is indicative and
nothing more.

Target 40-60 utterances. Record through the real browser capture path so the
eval audio matches production audio. Tag them:

| Tag | What it covers | Why it matters |
|---|---|---|
| `codeswitch` | mixing English with Mandarin/Malay | where engines diverge most |
| `dialect` | Hokkien, Teochew, Cantonese | **untested on every engine** |
| `elderly` | slow speech, mid-sentence pauses | the actual user |
| *(blank)* | ordinary English orders | the baseline |

About an hour of work. Then:

```bash
python -m stt.eval data/eval --engines singlish,whisper,polyglot
```

### 2. Curate the real menu

`data/catalogues/hawker.json` is invented. Replace it with the real one,
including every way a diner might say each item. Feeds both the biasing prompt
and the fuzzy matcher, so it improves accuracy twice. No coding.

### 3. Latency

Both CPU engines take ~2.6s per order. For an elderly diner that is a
noticeable wait, and it is the weakest part of the demo. The obvious experiment
is `polyglot` on Apple Silicon:

```bash
pip install mlx-qwen3-asr
./scripts/convert_polyglot_mlx.sh          # timebox to ~1 hour
python scripts/compare_engines.py --record --engines singlish,polyglot
```

If the conversion fails, run `--engines singlish,qwen` instead — base Qwen3-ASR
needs no conversion and shares the same code path.

### 4. Dialects — an open question worth answering

Nothing here has been tested on Hokkien or Teochew, and elderly diners are the
group most likely to use them. Polyglot-Lion was trained on four languages and
explicitly **not** on dialects; base Qwen3-ASR advertises Cantonese and Minnan;
MERaLiON claims Hokkien. Whether any of that survives in practice is
unpublished, so the `dialect` subset in step 1 answers something nobody has
written down. That is pitch material.

### 5. Tune the correction thresholds

`stt/correct.py` uses a fuzzy threshold of 82, and `stt/parse.py` uses 85 for
quantities with a 3-character minimum. Both were set against synthetic examples,
not real audio. Re-tune once the test set exists — this is where menu accuracy
is actually won.

## A note on what testing already caught

Real testing on real hardware found five bugs that unit tests and reasoning did
not. Worth remembering when deciding how much to trust the untested engines:

- A missing PyTorch dependency, surfacing as a bare `NameError` from inside
  ctranslate2
- A hardcoded `tokenizer.json` that aborted conversion for any checkpoint using
  the older `vocab.json` + `merges.txt` layout
- A comparison tool that silently compared one model against itself and printed
  identical lines that read as agreement
- Quantity matching so strict that "two" heard as "do" became 1x
- A fixed six-second recorder that truncated the speaker mid-order — in a
  project whose entire premise is that elderly speakers pause and need longer

The expectation that `singlish` would fail on code-switched speech was also
wrong, and only measurement showed it. Assume the same about anything else in
this README that has not been run.
