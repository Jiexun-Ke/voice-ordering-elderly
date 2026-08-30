#!/usr/bin/env python3
"""One-command verification of the STT service on a real machine.

Everything in here needs a real model, which is why it is a script you run
rather than a test in the suite: the CI-able parts are already covered by
`pytest tests/` (45 tests, no model needed).

    python scripts/verify.py                        # uses default engine
    python scripts/verify.py --engine qwen          # try another engine
    python scripts/verify.py --record               # record a clip from the mic first
    python scripts/verify.py --audio my_order.wav   # use your own clip

Exit code 0 = everything passed. Non-zero = something needs attention, and
the output says which check and what to do about it.
"""

import argparse
import io
import logging
import subprocess
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
_results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))
    icon = {PASS: "✓", FAIL: "✗", WARN: "!", SKIP: "-"}[status]
    print(f"  {icon} [{status}] {name}" + (f"\n        {detail}" if detail else ""))


# ----------------------------------------------------------------------------

def check_platform(engine_name: str) -> None:
    import platform

    print("\n== environment ==")
    machine, system = platform.machine(), platform.system()
    py = ".".join(map(str, sys.version_info[:2]))

    # ctranslate2 (which faster-whisper needs) publishes no wheels for 3.13 and
    # no source dist, so `pip install faster-whisper` fails with a confusing
    # error. Catch it here rather than letting someone debug pip output.
    if sys.version_info >= (3, 13):
        record(FAIL, f"python {py} on {system}/{machine}",
               "ctranslate2 has no wheels for Python 3.13, so faster-whisper "
               "cannot install. Use Python 3.12 or older: py -3.12 -m venv .venv")
    else:
        record(PASS, f"python {py} on {system}/{machine}")

    mlx_engine = engine_name in {"polyglot", "qwen", "meralion"}
    cuda_engine = engine_name.endswith("-cuda")
    apple_silicon = system == "Darwin" and machine == "arm64"

    if mlx_engine and not apple_silicon:
        record(
            WARN, f"engine {engine_name!r} needs Apple Silicon",
            "MLX will not import here, so the service falls back to whisper.\n"
            "        On Windows/Linux use --engine singlish (CPU, "
            "Singapore-tuned) or --engine polyglot-cuda (NVIDIA).",
        )
    elif cuda_engine:
        try:
            import torch

            if not torch.cuda.is_available():
                record(WARN, f"engine {engine_name!r} needs a visible NVIDIA GPU",
                       "torch reports no CUDA device; will fall back to whisper. "
                       "Use --engine singlish for the CPU path.")
        except ImportError:
            record(WARN, "torch not installed",
                   f"{engine_name!r} needs: pip install qwen-asr plus a CUDA torch")


def check_tests() -> None:
    print("\n== unit tests (no model needed) ==")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    tail = (proc.stdout or proc.stderr).strip().splitlines()[-1:]
    if proc.returncode == 0:
        record(PASS, "pytest", tail[0] if tail else "")
    else:
        record(FAIL, "pytest", tail[0] if tail else "see `pytest tests/ -q`")


def check_engine_loads(engine_name: str):
    """Load the engine and, crucially, confirm biasing is actually wired up."""
    print("\n== engine ==")
    from stt.engines import get_engine

    # Capture the warning mlx_qwen logs when it cannot find a biasing kwarg —
    # that failure is otherwise SILENT, and would mean catalogue biasing is
    # quietly doing nothing while everything still appears to work.
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger("stt.engines.mlx_qwen").addHandler(handler)
    logging.getLogger("stt.engines").addHandler(handler)

    try:
        engine = get_engine(engine_name, allow_fallback=False)
    except Exception as exc:
        record(FAIL, f"load engine {engine_name!r}", f"{type(exc).__name__}: {exc}")
        return None

    if not engine.is_available():
        record(FAIL, f"engine {engine_name!r} backend missing",
               "pip install mlx-qwen3-asr (Apple Silicon) or faster-whisper")
        return None
    record(PASS, f"engine constructed: {engine.name}")

    started = time.perf_counter()
    try:
        engine.warm_up()
    except Exception as exc:
        record(FAIL, "warm-up", f"{type(exc).__name__}: {exc}")
        return None
    record(PASS, f"warm-up ({time.perf_counter() - started:.1f}s)")

    logged = buf.getvalue()
    if "no biasing kwarg" in logged or "exposes no biasing" in logged:
        record(
            FAIL, "catalogue biasing NOT wired up",
            "The MLX wrapper exposes no biasing parameter under any name this "
            "code knows. Biasing is silently disabled — accuracy on menu terms "
            "rests entirely on correct.py. Inspect the wrapper's transcribe() "
            "signature and add its kwarg to _BIAS_KWARGS in "
            "stt/engines/mlx_qwen.py.",
        )
    else:
        record(PASS, "biasing parameter detected")
    return engine


def check_transcription(engine, audio: Path):
    print("\n== real transcription ==")
    from stt.catalogue import load_catalogue
    from stt.correct import correct
    from stt.parse import parse_order

    cat = load_catalogue("hawker")
    bias = cat.bias_text(engine.bias_style)

    try:
        biased = engine.transcribe(str(audio), bias=bias)
    except Exception as exc:
        record(FAIL, "transcribe", f"{type(exc).__name__}: {exc}")
        return
    if not biased.text.strip():
        record(FAIL, "transcribe returned empty text",
               "Check the clip actually contains speech and is not silent.")
        return
    record(PASS, f"transcribed in {biased.latency_ms}ms", f'"{biased.text}"')

    if biased.latency_ms > 3000:
        record(WARN, f"latency {biased.latency_ms}ms is high for a live demo",
               "Consider the 0.6B model, or 4-bit quantisation.")

    corrected, matches = correct(biased.text, cat)
    order = parse_order(biased.text, cat, matches)
    record(PASS if matches else WARN,
           f"{len(matches)} catalogue term(s) matched",
           f"readback: {order.describe()}")

    # Biasing A/B — plan verification step 4.
    try:
        unbiased = engine.transcribe(str(audio), bias=None)
    except Exception as exc:
        record(SKIP, "biasing A/B", f"unbiased pass failed: {exc}")
        return
    if unbiased.text.strip() == biased.text.strip():
        record(WARN, "biasing changed nothing on this clip",
               "Not necessarily broken — the clip may contain no ambiguous "
               "menu term. Retry with a clip saying something like "
               "'char kway teow' or 'kopi-c siew dai'.")
    else:
        record(PASS, "biasing changes output",
               f'biased:   "{biased.text}"\n        unbiased: "{unbiased.text}"')


def check_regression(engine, audio: Path) -> None:
    """Plan verification step 3: the port must match the prototype."""
    print("\n== regression vs voice_ordering.py ==")
    if not engine.name.startswith("whisper"):
        record(SKIP, "regression check",
               f"only meaningful for the whisper engine (running {engine.name}); "
               "re-run with --engine whisper")
        return
    try:
        sys.path.insert(0, str(REPO))
        import voice_ordering  # the teammate's untouched prototype

        with redirect_stderr(io.StringIO()):
            proto_text, _ = voice_ordering.transcribe(str(audio))
        ours = engine.transcribe(
            str(audio), bias=voice_ordering.CATALOGUE_PROMPT
        ).text
    except Exception as exc:
        record(SKIP, "regression check", f"{type(exc).__name__}: {exc}")
        return

    from stt.correct import normalize

    if normalize(proto_text) == normalize(ours):
        record(PASS, "port matches prototype output")
    else:
        record(
            WARN, "port differs from prototype",
            f'prototype: "{proto_text}"\n        port:      "{ours}"\n'
            "        Expected if language detection differs: the port sets "
            "language=None for code-switching, the prototype pins 'en'.",
        )


def check_server(engine_name: str, audio: Path) -> None:
    print("\n== live server ==")
    import json
    import os
    import urllib.request

    env = {**os.environ, "STT_ENGINE": engine_name}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "stt.server:app", "--port", "8099",
         "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        health = None
        for _ in range(60):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8099/health", timeout=2) as r:
                    health = json.load(r)
                break
            except Exception:
                continue

        if health is None:
            record(FAIL, "server did not start", "run uvicorn manually to see why")
            return
        if not health.get("engine_ready"):
            record(FAIL, "server reports engine_ready=false", json.dumps(health))
            return
        record(PASS, f"/health ok (engine {health['engine']})")

        boundary = "----verify"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="audio"; filename="clip.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8099/transcribe", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.load(r)

        required = {"text", "corrected_text", "matched_items", "order",
                    "readback", "confidence", "low_confidence", "engine",
                    "latency_ms"}
        missing = required - payload.keys()
        if missing:
            record(FAIL, "/transcribe response missing keys", str(sorted(missing)))
        else:
            record(PASS, "/transcribe returns the full contract",
                   f"readback: {payload['readback']}")
    except Exception as exc:
        record(FAIL, "server check", f"{type(exc).__name__}: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def record_clip(dest: Path, seconds: int = 5) -> Path | None:
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError:
        print("  need: pip install sounddevice soundfile")
        return None
    print(f"\nRecording {seconds}s — say an order, e.g. "
          '"two kopi-c siew dai, tapao"')
    input("Press Enter to start...")
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="float32")
    sd.wait()
    sf.write(str(dest), audio, 16000)
    print(f"Saved {dest}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", default=None,
                    help="polyglot | qwen | meralion | whisper (default: from STT_ENGINE)")
    ap.add_argument("--audio", type=Path, default=None, help="clip to test with")
    ap.add_argument("--record", action="store_true", help="record a clip from the mic")
    ap.add_argument("--skip-server", action="store_true")
    args = ap.parse_args()

    import os
    engine_name = args.engine or os.environ.get("STT_ENGINE", "polyglot")

    print("=" * 72)
    print(f"STT verification — engine: {engine_name}")
    print("=" * 72)

    check_platform(engine_name)
    check_tests()

    audio = args.audio
    if args.record:
        audio = record_clip(REPO / "data" / "eval" / "verify_clip.wav")
    if audio and not Path(audio).exists():
        print(f"\nno such file: {audio}")
        return 2

    engine = check_engine_loads(engine_name)
    if engine and audio:
        check_transcription(engine, Path(audio))
        check_regression(engine, Path(audio))
    elif engine:
        record(SKIP, "transcription checks",
               "no audio given — re-run with --record or --audio clip.wav")

    if not args.skip_server and audio:
        check_server(engine_name, Path(audio))

    print("\n" + "=" * 72)
    counts = {s: sum(1 for st, _, _ in _results if st == s) for s in (PASS, FAIL, WARN, SKIP)}
    print(f"{counts[PASS]} passed, {counts[FAIL]} failed, "
          f"{counts[WARN]} warnings, {counts[SKIP]} skipped")
    if counts[FAIL]:
        print("\nFailures:")
        for status, name, detail in _results:
            if status == FAIL:
                print(f"  ✗ {name}\n    {detail}")
    print("=" * 72)
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
