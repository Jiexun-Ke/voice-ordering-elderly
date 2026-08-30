"""MERaLiON-2-3B on Apple Silicon via mlx-meralion.

Not on the critical path. This exists so the Day 4 dialect probe is cheap:
MERaLiON explicitly claims Singlish, Hokkien and Cantonese coverage, which is
the one gap Polyglot-Lion has and the one most likely to matter for elderly
diners.

Caveat worth remembering when reading eval output: the widely-quoted 14.32
error rate belongs to MERaLiON-2-*10B*-ASR, not to this 3B model, whose
accuracy is unpublished. Judge it on our own recordings only.
"""

import importlib.util
import inspect
import logging
import time

from .base import ASREngine, TranscriptResult

log = logging.getLogger(__name__)

_BIAS_KWARGS = ("context", "prompt", "vocabulary", "hotwords")


class MLXMeralionEngine(ASREngine):
    bias_style = "vocabulary"

    def __init__(self, model: str = "MERaLiON/MERaLiON-2-3B-MLX"):
        self.model_id = model
        self._model = None
        self._transcribe = None
        self._bias_kwarg: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        from .mlx_qwen import _module_present

        return _module_present("mlx_meralion")

    @property
    def name(self) -> str:
        return f"{self.model_id.rstrip('/').split('/')[-1]}"

    def _load(self):
        if self._model is not None:
            return
        from mlx_meralion import load_model, transcribe  # type: ignore

        self._model = load_model(self.model_id)
        self._transcribe = transcribe
        try:
            params = inspect.signature(transcribe).parameters
            self._bias_kwarg = next(
                (k for k in _BIAS_KWARGS if k in params), None
            )
        except (TypeError, ValueError):
            self._bias_kwarg = None

    def warm_up(self) -> None:
        self._load()

    def transcribe(self, audio_path: str, bias: str | None = None) -> TranscriptResult:
        self._load()
        kwargs = {}
        if bias and self._bias_kwarg:
            kwargs[self._bias_kwarg] = bias

        started = time.perf_counter()
        result = self._transcribe(self._model, str(audio_path), **kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = result if isinstance(result, str) else getattr(result, "text", "")
        return TranscriptResult(
            text=str(text).strip(),
            confidence=None,
            engine=self.name,
            latency_ms=latency_ms,
        )
