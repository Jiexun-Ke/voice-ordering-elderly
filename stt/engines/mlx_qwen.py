"""Qwen3-ASR family on Apple Silicon via MLX.

Covers BOTH `knoveleng/polyglot-lion-1.7b` (Singapore fine-tune, our default)
and `Qwen/Qwen3-ASR-1.7B` (the base model, which advertises Cantonese and
Minnan). They are the same architecture, so one class serves both and the
Day 4 dialect probe is a model-id change.

Two MLX packages for this family exist in the wild and their APIs differ
slightly, so we detect whichever is installed and introspect for the biasing
keyword rather than hardcoding one. This costs ~20 lines and removes a whole
class of "works on my machine" failure.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import time
from typing import Any, Callable

from .base import ASREngine, TranscriptResult

log = logging.getLogger(__name__)

# Ordered by preference. Qwen3-ASR takes biasing vocabulary through its system
# prompt; different wrappers surface that under different names.
_BIAS_KWARGS = ("context", "prompt", "hotwords", "initial_prompt", "vocabulary")


class MLXQwenEngine(ASREngine):
    # Practitioner testing found the framing words matter for Qwen3-ASR:
    # "Vocabulary:" / "Proper nouns:" measurably beat "Terms:" or "Context:".
    bias_style = "vocabulary"

    def __init__(self, model: str = "knoveleng/polyglot-lion-1.7b"):
        self.model_id = model
        self._session: Any = None
        self._transcribe_fn: Callable[..., Any] | None = None
        self._bias_kwarg: str | None = None
        self._backend: str | None = None

    #: Either wrapper package is acceptable; we adapt to whichever is present.
    BACKENDS = ("mlx_qwen3_asr", "qwen3_asr_mlx")

    @classmethod
    def is_available(cls) -> bool:
        return any(_module_present(m) for m in cls.BACKENDS)

    @property
    def name(self) -> str:
        short = self.model_id.rstrip("/").split("/")[-1]
        return f"{short}-mlx"

    def _load(self) -> Callable[..., Any]:
        """Import and instantiate on first use, returning the transcribe fn.

        Returning it (rather than only setting an attribute) keeps the call
        site provably non-None for type checkers and readers alike.
        """
        if self._transcribe_fn is not None:
            return self._transcribe_fn

        session, backend = None, None
        try:
            from mlx_qwen3_asr import Session  # type: ignore

            session, backend = Session(model=self.model_id), "mlx_qwen3_asr"
        except ImportError:
            from qwen3_asr_mlx import Qwen3ASR  # type: ignore

            session = Qwen3ASR.from_pretrained(self.model_id)
            backend = "qwen3_asr_mlx"

        self._session = session
        self._backend = backend
        self._transcribe_fn = session.transcribe
        self._bias_kwarg = self._detect_bias_kwarg(session.transcribe)
        if self._bias_kwarg is None:
            log.warning(
                "%s exposes no biasing kwarg; catalogue biasing is disabled for "
                "this engine and accuracy on menu terms will rely on correct.py",
                backend,
            )
        return self._transcribe_fn

    @staticmethod
    def _detect_bias_kwarg(fn) -> str | None:
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            return None
        # A **kwargs-only signature tells us nothing; assume the documented name.
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return _BIAS_KWARGS[0]
        for candidate in _BIAS_KWARGS:
            if candidate in params:
                return candidate
        return None

    def warm_up(self) -> None:
        self._load()

    def transcribe(self, audio_path: str, bias: str | None = None) -> TranscriptResult:
        transcribe_fn = self._load()

        kwargs = {}
        if bias and self._bias_kwarg:
            kwargs[self._bias_kwarg] = bias

        started = time.perf_counter()
        result = transcribe_fn(str(audio_path), **kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return TranscriptResult(
            text=_extract_text(result).strip(),
            # MLX wrappers do not surface a log-probability. base.py treats a
            # missing confidence as "unknown", not "bad", so this does not
            # spuriously trigger re-asks.
            confidence=None,
            engine=self.name,
            latency_ms=latency_ms,
        )


def _extract_text(result) -> str:
    """Both wrappers return a result object; one older path returns a str."""
    if isinstance(result, str):
        return result
    for attr in ("text", "transcript"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    if isinstance(result, dict):
        for key in ("text", "transcript"):
            if isinstance(result.get(key), str):
                return result[key]
    raise TypeError(f"cannot extract text from {type(result).__name__}")


def _module_present(name: str) -> bool:
    """Importable check that survives a missing parent package."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
