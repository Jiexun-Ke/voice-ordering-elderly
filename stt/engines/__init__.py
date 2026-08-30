"""Engine registry and factory.

Engines are constructed lazily and imported inside the factory so that
importing this package never requires MLX, CUDA, or any model to be present.
That matters because teammates on Windows or Intel Macs still need to run the
tests and the catalogue/correction layers.
"""

import logging
import os

from .base import ASREngine, TranscriptResult, LOW_CONFIDENCE_THRESHOLD

log = logging.getLogger(__name__)

# A Singlish-finetuned Whisper converted to CTranslate2. Runs on CPU on every
# platform — the only Singapore-tuned option available to teammates on Windows
# or Intel Macs. Produced by scripts/convert_singlish.py; WhisperEngine falls
# back to the generic model if it has not been created yet.
SINGLISH_CT2_DIR = "models/singlish-ct2"

# name -> (module attr, default model id)
# The two MLX Qwen entries are the SAME class with a different model id, which
# is exactly why the Day 4 dialect probe costs one config change.
REGISTRY = {
    # Apple Silicon (MLX)
    "polyglot": ("mlx_qwen", "knoveleng/polyglot-lion-1.7b"),
    "qwen": ("mlx_qwen", "Qwen/Qwen3-ASR-1.7B"),
    "meralion": ("mlx_meralion", "MERaLiON/MERaLiON-2-3B-MLX"),
    # NVIDIA (official qwen-asr package) — Windows or Linux with CUDA
    "polyglot-cuda": ("cuda_qwen", "knoveleng/polyglot-lion-1.7b"),
    "qwen-cuda": ("cuda_qwen", "Qwen/Qwen3-ASR-1.7B"),
    # CPU, every platform including Windows (CTranslate2)
    "singlish": ("whisper", SINGLISH_CT2_DIR),
    "whisper": ("whisper", "small"),
}

DEFAULT_ENGINE = "polyglot"
FALLBACK_ENGINE = "whisper"


def _build(name: str, model: str | None) -> ASREngine:
    module_name, default_model = REGISTRY[name]
    model = model or os.environ.get("STT_MODEL") or default_model

    if module_name == "mlx_qwen":
        from .mlx_qwen import MLXQwenEngine

        return MLXQwenEngine(model=model)
    if module_name == "mlx_meralion":
        from .mlx_meralion import MLXMeralionEngine

        return MLXMeralionEngine(model=model)
    if module_name == "cuda_qwen":
        from .cuda_qwen import CUDAQwenEngine

        return CUDAQwenEngine(model=model)
    if module_name == "whisper":
        from .whisper import WhisperEngine

        return WhisperEngine(model=model)
    raise ValueError(f"unmapped engine module: {module_name}")


def get_engine(name: str | None = None, model: str | None = None,
               allow_fallback: bool = True) -> ASREngine:
    """Return a ready engine, falling back to CPU Whisper if the primary fails.

    The fallback exists because the MLX path is Apple-Silicon-only and the
    Polyglot-Lion MLX conversion is undocumented. A demo that quietly runs on
    a weaker engine beats a demo that 500s.
    """
    name = (name or os.environ.get("STT_ENGINE") or DEFAULT_ENGINE).lower()
    if name not in REGISTRY:
        raise ValueError(
            f"unknown engine {name!r}; choose from {sorted(REGISTRY)}"
        )

    try:
        engine = _build(name, model)
        if not engine.is_available():
            raise RuntimeError(
                f"{name} engine has no usable backend installed on this machine"
            )
        return engine
    except Exception as exc:  # noqa: BLE001 - any failure should degrade, not crash
        if not allow_fallback or name == FALLBACK_ENGINE:
            raise
        log.warning(
            "engine %r unavailable (%s: %s); falling back to %r",
            name, type(exc).__name__, exc, FALLBACK_ENGINE,
        )
        return _build(FALLBACK_ENGINE, None)


__all__ = [
    "ASREngine",
    "SINGLISH_CT2_DIR",
    "TranscriptResult",
    "LOW_CONFIDENCE_THRESHOLD",
    "REGISTRY",
    "DEFAULT_ENGINE",
    "get_engine",
]
