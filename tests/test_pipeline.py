"""Tests that run with no model, no GPU and no network.

Everything except the ASR model itself is covered here, which is the point:
teammates on any platform can run these, and a broken catalogue or parser is
caught without waiting on a download.
"""

import numpy as np
import pytest
import soundfile as sf

from stt.audio import AudioError, to_wav16k_mono
from stt.catalogue import MAX_BIAS_TOKENS, load_catalogue
from stt.correct import correct, find_matches
from stt.engines.base import ASREngine, TranscriptResult
from stt.parse import parse_order


@pytest.fixture(scope="module")
def hawker():
    return load_catalogue("hawker")


# ---------- catalogue ----------

def test_both_catalogues_load():
    for name in ("hawker", "grocery"):
        cat = load_catalogue(name)
        assert cat.items and cat.modifiers


def test_bias_text_respects_token_budget(hawker):
    for style in ("vocabulary", "sentence"):
        text = hawker.bias_text(style)
        assert len(text) // 4 <= MAX_BIAS_TOKENS


def test_bias_style_changes_framing(hawker):
    # Qwen3-ASR is measurably sensitive to the framing words, so the two
    # styles must not collapse into the same string.
    assert hawker.bias_text("vocabulary").startswith("Vocabulary:")
    assert hawker.bias_text("sentence").startswith("Food order.")


def test_alias_lookup_is_case_insensitive(hawker):
    assert hawker.lookup("Kopi See").canonical == "KOPI_C"


# ---------- correction ----------

@pytest.mark.parametrize("spoken,expected", [
    ("char kuey teow", "CHAR_KWAY_TEOW"),   # alias
    ("char kway tio", "CHAR_KWAY_TEOW"),    # unseen ASR corruption
    ("wan tan mee", "WANTON_MEE"),
    ("kopi see", "KOPI_C"),
    ("sew dai", "SIEW_DAI"),
    ("da pao", "TAKEAWAY"),
    ("nasi lemah", "NASI_LEMAK"),
])
def test_fuzzy_recovers_asr_errors(hawker, spoken, expected):
    assert any(m.canonical == expected for m in find_matches(spoken, hawker))


def test_unrelated_speech_matches_nothing(hawker):
    assert find_matches("hello how are you today", hawker) == []


def test_longer_terms_beat_their_own_prefixes(hawker):
    # "kopi c" must win over a bare "kopi".
    matches = find_matches("one kopi c please", hawker)
    assert [m.canonical for m in matches] == ["KOPI_C"]


# ---------- parsing ----------

def test_quantity_and_postfix_modifier(hawker):
    order = parse_order("two kopi c siew dai tapao", hawker)
    assert order.takeaway is True
    assert len(order.lines) == 1
    line = order.lines[0]
    assert (line.canonical, line.quantity, line.modifiers) == (
        "KOPI_C", 2, ["siew dai"]
    )


def test_code_switched_quantity(hawker):
    order = parse_order("dua kopi peng", hawker)
    assert order.lines[0].quantity == 2


def test_digit_quantity_and_multiple_lines(hawker):
    order = parse_order("wan tan mee gau and 2 kaya toast", hawker)
    assert [(l.canonical, l.quantity) for l in order.lines] == [
        ("WANTON_MEE", 1), ("KAYA_TOAST", 2)
    ]


def test_total_multiplies_by_quantity(hawker):
    order = parse_order("three teh o", hawker)
    assert order.total == pytest.approx(3 * 1.10)


def test_empty_order_is_graceful(hawker):
    order = parse_order("nice weather today", hawker)
    assert order.lines == [] and order.describe() == "nothing recognised"


# ---------- audio ----------

def _write(path, seconds, rate=16000, channels=1):
    t = np.linspace(0, seconds, int(rate * seconds), dtype="float32")
    tone = np.sin(2 * np.pi * 440 * t)
    data = np.stack([tone] * channels, axis=1) if channels > 1 else tone
    sf.write(str(path), data, rate)
    return path


def test_downmix_and_resample(tmp_path):
    out = to_wav16k_mono(_write(tmp_path / "in.wav", 1.0, 44100, 2))
    info = sf.info(str(out))
    assert (info.samplerate, info.channels) == (16000, 1)


def test_rejects_too_short_audio(tmp_path):
    with pytest.raises(AudioError, match="at least"):
        to_wav16k_mono(_write(tmp_path / "tiny.wav", 0.05))


def test_rejects_missing_file(tmp_path):
    with pytest.raises(AudioError, match="no such audio"):
        to_wav16k_mono(tmp_path / "nope.wav")


# ---------- engine contract ----------

def test_missing_confidence_is_not_low_confidence():
    # MLX engines expose no logprob. Unknown must not read as bad, or elderly
    # users get spurious re-asks on every single order.
    result = TranscriptResult(text="kopi", engine="stub", latency_ms=1)
    assert result.confidence is None and result.low_confidence is False


def test_bad_confidence_flags_low_confidence():
    result = TranscriptResult(
        text="???", engine="stub", latency_ms=1, confidence=-2.5
    )
    assert result.low_confidence is True


def test_engine_subclass_satisfies_contract():
    class Stub(ASREngine):
        name = "stub"

        def transcribe(self, audio_path, bias=None):
            return TranscriptResult(text="two kopi c", engine="stub", latency_ms=5)

    assert Stub().transcribe("x").text == "two kopi c"


# ---------- engine availability ----------

def test_lazy_import_means_construction_proves_nothing():
    # Regression: engines import their backend in _load(), so constructing an
    # MLX engine on a non-Mac SUCCEEDS. If the factory trusted construction it
    # would hand back an engine that 500s on the first real request.
    from stt.engines.mlx_qwen import MLXQwenEngine

    engine = MLXQwenEngine()          # must not raise anywhere
    assert engine.is_available() is False  # ...but must report the truth


def test_factory_falls_back_when_backend_missing(caplog):
    from stt.engines import get_engine

    engine = get_engine("polyglot")
    assert not engine.name.endswith("-mlx"), "should have fallen back off MLX"


def test_factory_can_refuse_instead_of_falling_back():
    import pytest as _pytest

    from stt.engines import get_engine

    with _pytest.raises(RuntimeError, match="no usable backend"):
        get_engine("polyglot", allow_fallback=False)
