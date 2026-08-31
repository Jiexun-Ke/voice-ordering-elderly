"""The engine contract.

Everything downstream — the server, the eval harness, the correction layer —
talks to this interface and never to a specific model. That is what makes
swapping models a config change rather than a rewrite, which is the whole
reason we can commit to one engine now and still change our mind on Day 4.
"""


from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Matches the heuristic in voice_ordering.py: avg_logprob below about -1.0 is
# usually garbage. Drives the "please confirm" re-ask, which matters more for
# elderly users than raw accuracy does.
LOW_CONFIDENCE_THRESHOLD = -1.0


@dataclass
class TranscriptResult:
    """What every engine returns, regardless of the model behind it."""

    text: str
    engine: str
    latency_ms: int
    # Mean log-probability. Closer to 0 is more confident. None when the
    # backend does not expose one (the MLX engines do not) — in that case we
    # deliberately do NOT flag low confidence, because a missing signal is not
    # evidence of a bad transcript and spurious re-asks frustrate elderly users.
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def low_confidence(self) -> bool:
        if self.confidence is None:
            return False
        return self.confidence < LOW_CONFIDENCE_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "low_confidence": self.low_confidence,
            "engine": self.engine,
            "latency_ms": self.latency_ms,
            "warnings": self.warnings,
        }


class ASREngine(ABC):
    """Audio in, transcript out.

    `bias` is free-form vocabulary text used to tilt decoding toward catalogue
    terms. Both engine families support this — Whisper via `initial_prompt`,
    Qwen3-ASR via its `context` system prompt — but they want different
    phrasing, so catalogue.py formats it per engine rather than each engine
    inventing its own.
    """

    #: Which biasing dialect catalogue.py should emit for this engine.
    bias_style: str = "sentence"

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier that appears in API responses and eval tables."""

    @abstractmethod
    def transcribe(self, audio_path: str, bias: str | None = None) -> TranscriptResult:
        ...

    @classmethod
    def is_available(cls) -> bool:
        """Can this engine actually run here?

        Engines import their backend lazily so that constructing one is cheap
        and never platform-gated. That means construction succeeding proves
        nothing, so the factory asks this before handing an engine out —
        otherwise a machine without MLX would start up happily and only fail
        on the first real request, which is the worst possible moment.
        """
        return True

    def warm_up(self) -> None:
        """Load weights ahead of the first real request.

        The first MLX inference pays the whole weight-load cost. Doing that
        during startup rather than while a diner is standing at the counter is
        the difference between a 0.3s response and a 20s one.
        """
        return None
