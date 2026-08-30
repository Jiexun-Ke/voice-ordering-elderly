"""The eval harness is the artifact that picks the shipped model, so it needs
to work before Day 4 — not be debugged on the day the decision is due."""

import numpy as np
import pytest
import soundfile as sf

from stt import eval as stt_eval
from stt.engines.base import ASREngine, TranscriptResult


class ScriptedEngine(ASREngine):
    """Returns a canned transcript per filename, so WER is predictable."""

    bias_style = "vocabulary"

    def __init__(self, name, script, latency=42):
        self._name = name
        self.script = script
        self.latency = latency

    @property
    def name(self):
        return self._name

    def transcribe(self, audio_path, bias=None):
        from pathlib import Path
        key = Path(audio_path).name
        # Biasing "helps": unbiased output is deliberately degraded.
        text = self.script[key] if bias else self.script[key].replace("kway", "kuey")
        return TranscriptResult(
            text=text, engine=self._name, latency_ms=self.latency
        )


@pytest.fixture
def eval_dir(tmp_path):
    rows = [
        ("a.wav", "two kopi c siew dai", "elderly"),
        ("b.wav", "one char kway teow", "dialect"),
        ("c.wav", "three teh o kosong", ""),
    ]
    for name, _, _ in rows:
        t = np.linspace(0, 1, 16000, dtype="float32")
        sf.write(str(tmp_path / name), np.sin(2 * np.pi * 300 * t), 16000)

    with open(tmp_path / "refs.csv", "w") as fh:
        fh.write("filename,reference,tag\n")
        for name, ref, tag in rows:
            fh.write(f"{name},{ref},{tag}\n")
    return tmp_path


def test_eval_runs_and_reports_both_bias_settings(eval_dir, monkeypatch):
    script = {
        "a.wav": "two kopi c siew dai",
        "b.wav": "one char kway teow",
        "c.wav": "three teh o kosong",
    }
    monkeypatch.setattr(
        stt_eval, "get_engine",
        lambda name, **kw: ScriptedEngine(f"{name}-stub", script),
    )

    results = stt_eval.run(eval_dir, ["polyglot"], "hawker")

    assert ("polyglot-stub", True) in results
    assert ("polyglot-stub", False) in results
    # Perfect transcripts when biased; degraded when not.
    assert results[("polyglot-stub", True)]["wer"] == pytest.approx(0.0)
    assert results[("polyglot-stub", False)]["wer"] > 0
    assert results[("polyglot-stub", True)]["n"] == 3


def test_correction_recovers_the_unbiased_degradation(eval_dir, monkeypatch):
    # "kuey" is not a reference spelling, but correct.py maps it back — so
    # WER+fix should beat raw WER. This is the whole argument for correct.py.
    script = {
        "a.wav": "two kopi c siew dai",
        "b.wav": "one char kway teow",
        "c.wav": "three teh o kosong",
    }
    monkeypatch.setattr(
        stt_eval, "get_engine",
        lambda name, **kw: ScriptedEngine("stub", script),
    )
    results = stt_eval.run(eval_dir, ["polyglot"], "hawker")
    unbiased = results[("stub", False)]
    assert unbiased["wer_corrected"] < unbiased["wer"]


def test_tagged_subsets_are_broken_out(eval_dir, monkeypatch):
    script = {k: v for k, v in [
        ("a.wav", "two kopi c siew dai"),
        ("b.wav", "one char kway teow"),
        ("c.wav", "three teh o kosong"),
    ]}
    monkeypatch.setattr(
        stt_eval, "get_engine",
        lambda name, **kw: ScriptedEngine("stub", script),
    )
    results = stt_eval.run(eval_dir, ["polyglot"], "hawker")
    tags = results[("stub", True)]["by_tag"]
    assert set(tags) == {"elderly", "dialect"}


def test_missing_refs_csv_exits_with_guidance(tmp_path):
    with pytest.raises(SystemExit, match="Day 3 gate"):
        stt_eval.run(tmp_path, ["whisper"], "hawker")


def test_engine_that_fails_to_load_is_skipped_not_fatal(eval_dir, monkeypatch):
    def boom(name, **kw):
        raise RuntimeError("no MLX on this platform")

    monkeypatch.setattr(stt_eval, "get_engine", boom)
    # Should print a warning and return empty, not crash the whole bake-off.
    assert stt_eval.run(eval_dir, ["polyglot"], "hawker") == {}


def test_refs_csv_tolerates_comments_and_blanks(tmp_path, monkeypatch):
    # The shipped template is annotated with # comments; parsing them as
    # filenames would make the harness try to open "# Day 3 gate...".
    t = np.linspace(0, 1, 16000, dtype="float32")
    sf.write(str(tmp_path / "a.wav"), np.sin(2 * np.pi * 300 * t), 16000)
    (tmp_path / "refs.csv").write_text(
        "filename,reference,tag\n"
        "# this is a comment and must be ignored\n"
        "\n"
        "a.wav,two kopi c,elderly\n"
    )
    monkeypatch.setattr(
        stt_eval, "get_engine",
        lambda name, **kw: ScriptedEngine("stub", {"a.wav": "two kopi c"}),
    )
    results = stt_eval.run(tmp_path, ["polyglot"], "hawker")
    assert results[("stub", True)]["n"] == 1


def test_header_only_refs_csv_exits(tmp_path):
    (tmp_path / "refs.csv").write_text("filename,reference,tag\n# nothing yet\n")
    with pytest.raises(SystemExit, match="no data rows"):
        stt_eval.run(tmp_path, ["whisper"], "hawker")
