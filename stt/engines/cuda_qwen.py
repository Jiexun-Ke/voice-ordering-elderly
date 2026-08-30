"""Qwen3-ASR family on NVIDIA GPUs via the official `qwen-asr` package.

The MLX engines cover Apple Silicon; this covers everything with CUDA —
notably a Windows gaming laptop, which is what a teammate is likely to have,
and any rented cloud GPU. Same models, same catalogue biasing, different
runtime.

    pip install -U qwen-asr        # plus a CUDA-enabled torch

Falls in the same family as mlx_qwen.py deliberately: one model id switches
between Polyglot-Lion and base Qwen3-ASR, so the Day 4 dialect probe works
identically on whichever hardware the team ends up using.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import time
from typing import Any, Callable

from .base import ASREngine, TranscriptResult

log = logging.getLogger(__name__)

_BIAS_KWARGS = ("context", "prompt", "hotwords", "initial_prompt", "vocabulary")


def _cuda_ready() -> bool:
    """True only if torch is present AND a GPU is actually visible.

    Checking the import alone is not enough: a CPU-only torch install is
    common on Windows, and this engine would then load and fail at the first
    request rather than falling back cleanly.
    """
    try:
        if importlib.util.find_spec("qwen_asr") is None:
            return False
        import torch  # noqa: PLC0415

        return bool(torch.cuda.is_available())
    except (ImportError, ValueError, AttributeError):
        return False


class CUDAQwenEngine(ASREngine):
    bias_style = "vocabulary"

    def __init__(self, model: str = "knoveleng/polyglot-lion-1.7b",
                 device: str = "cuda:0"):
        self.model_id = model
        self.device = device
        self._model: Any = None
        self._bias_kwarg: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        return _cuda_ready()

    @property
    def name(self) -> str:
        return f"{self.model_id.rstrip('/').split('/')[-1]}-cuda"

    def _load(self) -> Callable[..., Any]:
        if self._model is not None:
            return self._model.transcribe

        import torch  # noqa: PLC0415
        from qwen_asr import Qwen3ASRModel  # type: ignore

        self._model = Qwen3ASRModel.from_pretrained(
            self.model_id,
            dtype=torch.bfloat16,
            device_map=self.device,
            max_new_tokens=256,
        )
        try:
            params = inspect.signature(self._model.transcribe).parameters
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                self._bias_kwarg = _BIAS_KWARGS[0]
            else:
                self._bias_kwarg = next(
                    (k for k in _BIAS_KWARGS if k in params), None
                )
        except (TypeError, ValueError):
            self._bias_kwarg = None

        if self._bias_kwarg is None:
            log.warning(
                "qwen-asr exposes no biasing kwarg; catalogue biasing is "
                "disabled and menu accuracy rests on correct.py alone"
            )
        return self._model.transcribe

    def warm_up(self) -> None:
        self._load()

    def transcribe(self, audio_path: str, bias: str | None = None) -> TranscriptResult:
        transcribe_fn = self._load()

        kwargs: dict[str, Any] = {"language": None}
        if bias and self._bias_kwarg:
            kwargs[self._bias_kwarg] = bias

        started = time.perf_counter()
        result = transcribe_fn(audio=str(audio_path), **kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return TranscriptResult(
            text=_extract_text(result).strip(),
            confidence=None,
            engine=self.name,
            latency_ms=latency_ms,
        )


def _extract_text(result: Any) -> str:
    """qwen-asr returns a list for batch calls and an object for single ones."""
    if isinstance(result, list):
        result = result[0] if result else ""
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
