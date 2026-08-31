"""faster-whisper engine — the runs-anywhere fallback.

This is a PORT of the logic in voice_ordering.py, not a rewrite of it. That
file belongs to a teammate and is left untouched; the tuned parameters below
are copied deliberately and the reasons are preserved with them, because they
encode real findings about elderly speech.

CTranslate2 supports CUDA and CPU only — there is no Metal/MPS path, so on
Apple Silicon this runs on CPU. That is fine: this engine exists so that
teammates on Windows and Intel Macs are never blocked, not to be fast.
"""


import logging
import os
import time
from pathlib import Path

from .base import ASREngine, TranscriptResult

log = logging.getLogger(__name__)

# Below this, faster-whisper reliably hallucinates text out of silence.
MIN_AUDIO_SECONDS = 0.35

# Generic fallback when a requested local checkpoint has not been built yet.
FALLBACK_MODEL = "small"


def _resolve_model(model: str) -> str:
    """Accept either a hub name ("small") or a local CTranslate2 directory.

    A path is only usable once scripts/convert_singlish.py has produced it, so
    a missing directory degrades to the generic model with a loud warning
    rather than an ImportError at first request. This is what lets `singlish`
    be the documented default on Windows before anyone has run the converter.
    """
    looks_like_path = "/" in model or os.sep in model
    if not looks_like_path:
        return model
    if Path(model).is_dir():
        return model
    log.warning(
        "checkpoint %r not found; falling back to %r. Build it with: "
        "python scripts/convert_singlish.py",
        model, FALLBACK_MODEL,
    )
    return FALLBACK_MODEL


class WhisperEngine(ASREngine):
    bias_style = "sentence"

    def __init__(self, model: str = "small", device: str | None = None,
                 compute_type: str | None = None):
        self.model_id = _resolve_model(model)
        # Overridable so the same code serves a CUDA box (e.g. an NVIDIA
        # laptop) without a second engine class.
        self.device = device or os.environ.get("STT_WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.environ.get(
            "STT_WHISPER_COMPUTE", "int8"
        )
        self._model = None

    @classmethod
    def is_available(cls) -> bool:
        from .mlx_qwen import _module_present

        return _module_present("faster_whisper")

    @property
    def name(self) -> str:
        return f"whisper-{self.model_id}"

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_id, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def warm_up(self) -> None:
        self._load()

    def transcribe(self, audio_path: str, bias: str | None = None) -> TranscriptResult:
        model = self._load()

        started = time.perf_counter()
        segments, _info = model.transcribe(
            str(audio_path),
            # The prototype pinned language="en". Code-switching is a hard
            # requirement here, so we let Whisper detect instead.
            language=None,
            beam_size=5,
            vad_filter=True,
            # Elderly speakers pause mid-sentence. The default 500ms endpoint
            # chops them off, so give it a much longer tail.
            vad_parameters={"min_silence_duration_ms": 2000},
            initial_prompt=bias or None,
        )
        segments = list(segments)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if not segments:
            return TranscriptResult(
                text="",
                confidence=-99.0,
                engine=self.name,
                latency_ms=latency_ms,
                warnings=["no_speech_detected"],
            )

        text = " ".join(s.text.strip() for s in segments).strip()
        confidence = sum(s.avg_logprob for s in segments) / len(segments)
        return TranscriptResult(
            text=text,
            confidence=confidence,
            engine=self.name,
            latency_ms=latency_ms,
        )
