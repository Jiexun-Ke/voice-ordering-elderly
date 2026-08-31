"""Voice-ordering STT service.

Sets HF_HOME before any model library is imported so that downloaded weights
land inside the repository rather than in ~/.cache/huggingface. That keeps the
whole project — code, catalogues, models, eval audio — in one directory you can
move to another drive without breaking anything.

Override by setting HF_HOME yourself before importing, e.g. to share one cache
across several projects.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf-cache"))

__all__ = ["REPO_ROOT", "MODELS_DIR"]
