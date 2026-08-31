"""FastAPI service: the contract the rest of the team builds against.

Deliberately stands up before any model is finalised. The JSON shape below is
frozen on Day 1 so the frontend, backend and NLP work can proceed in parallel
against a mock; swapping the engine underneath changes nothing here.

Run:
    uvicorn stt.server:app --reload --host 0.0.0.0 --port 8000

Config (env):
    STT_ENGINE     singlish | polyglot | polyglot-cuda | qwen | meralion | whisper
                   (default: singlish — runs on every platform)
    STT_MODEL      override the model id for that engine
    STT_CATALOGUE  catalogue name or path                 (default: hawker)
"""


import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .audio import AudioError, ffmpeg_available, to_wav16k_mono
from .catalogue import load_catalogue
from .correct import correct
from .engines import DEFAULT_ENGINE, get_engine
from .parse import parse_order

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stt.server")

DEFAULT_CATALOGUE = os.environ.get("STT_CATALOGUE", "hawker")

_state: dict = {"engine": None, "catalogues": {}}


def _catalogue(name: str):
    """Cache catalogues by name; they are small and read on every request."""
    if name not in _state["catalogues"]:
        try:
            _state["catalogues"][name] = load_catalogue(name)
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(404, f"unknown catalogue {name!r}") from exc
    return _state["catalogues"][name]


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    _state["engine"] = engine
    log.info("engine selected: %s", engine.name)
    try:
        # Pay the weight-load cost now, not while a diner is at the counter.
        engine.warm_up()
        log.info("engine warm")
    except Exception as exc:  # noqa: BLE001
        log.warning("warm-up failed (%s); first request will be slow", exc)
    yield


app = FastAPI(title="Voice Ordering STT", version="0.1.0", lifespan=lifespan)

# Wide open: hackathon frontends run from file://, ngrok tunnels and phones on
# the venue wifi. Tighten before this is ever public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Reports readiness honestly.

    The service deliberately starts even with no ASR backend installed, so
    that teammates can build against /catalogue and the response contract on
    any machine. But it must not claim an engine it cannot run — `engine_ready`
    is the field to trust, and /transcribe 503s when it is false.
    """
    engine = _state["engine"]
    ready = bool(engine) and engine.is_available()
    return {
        "status": "ok" if ready else "degraded",
        "engine": engine.name if engine else None,
        "engine_ready": ready,
        "engine_requested": os.environ.get("STT_ENGINE", DEFAULT_ENGINE),
        "catalogue": DEFAULT_CATALOGUE,
        "ffmpeg": ffmpeg_available(),
    }


@app.get("/catalogue")
def get_catalogue(name: str = Query(DEFAULT_CATALOGUE)):
    cat = _catalogue(name)
    return {
        "merchant": cat.merchant,
        "id": cat.merchant_id,
        "items": [
            {"canonical": e.canonical, "display": e.display, "price": e.price}
            for e in cat.items
        ],
        "modifiers": [
            {"canonical": e.canonical, "display": e.display} for e in cat.modifiers
        ],
    }


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    catalogue: str = Query(DEFAULT_CATALOGUE),
    bias: bool = Query(True, description="Set false to A/B catalogue biasing"),
):
    engine = _state["engine"]
    if engine is None:
        raise HTTPException(503, "engine not ready")
    if not engine.is_available():
        raise HTTPException(
            503,
            f"no ASR backend installed for engine {engine.name!r}. On Apple "
            "Silicon: pip install mlx-qwen3-asr. Elsewhere: pip install "
            "faster-whisper and set STT_ENGINE=whisper.",
        )

    cat = _catalogue(catalogue)
    suffix = Path(audio.filename or "clip.wav").suffix or ".wav"

    raw = Path(tempfile.mkstemp(suffix=suffix, prefix="upload_")[1])
    wav = None
    try:
        raw.write_bytes(await audio.read())
        try:
            wav = to_wav16k_mono(raw)
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from exc

        bias_text = cat.bias_text(engine.bias_style) if bias else None
        result = engine.transcribe(str(wav), bias=bias_text)

        corrected_text, matches = correct(result.text, cat)
        order = parse_order(result.text, cat, matches)

        return {
            **result.to_dict(),
            "corrected_text": corrected_text,
            "matched_items": [m.to_dict() for m in matches],
            "order": order.to_dict(),
            "readback": order.describe(),
            "catalogue": cat.merchant_id,
            "biased": bool(bias_text),
        }
    finally:
        raw.unlink(missing_ok=True)
        if wav is not None and Path(wav) != raw:
            Path(wav).unlink(missing_ok=True)
