#!/usr/bin/env python3
"""Run one clip through every available engine, side by side.

Built to answer a specific open question: `singlish` is finetuned on a
Singapore *English* corpus, and finetuning Whisper on English-heavy data is
documented to damage its multilingual ability — so it may handle
"two kopi-c siew dai" well and fall apart on "我要两杯 kopi". Nobody has
published a code-switching evaluation of that checkpoint, so measure it.

    python scripts/compare_engines.py --record
    python scripts/compare_engines.py clip1.wav clip2.wav
    python scripts/compare_engines.py --engines singlish,whisper,polyglot clip.wav

Unlike `stt.eval`, this needs no refs.csv — it prints transcripts for eyeballing
rather than computing WER. Use it to decide what to record; use stt.eval once
you have a labelled set.
"""


import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stt.catalogue import load_catalogue  # noqa: E402
from stt.correct import correct  # noqa: E402
from stt.engines import REGISTRY, get_engine  # noqa: E402
from stt.parse import parse_order  # noqa: E402

DEFAULT_ENGINES = "singlish,whisper,polyglot"


def record_clip(dest: Path) -> Path | None:
    try:
        from stt.audio import record_until_enter
    except ImportError:
        print("need: pip install sounddevice soundfile")
        return None
    return record_until_enter(dest, prompt=(
        "\nSay a code-switched order — that is the case in question, e.g.\n"
        '  "我要两杯 kopi, 少甜"   or   "wo yao two kopi-c siew dai, tapao"'
    ))


def find_collisions(resolved: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Map model name -> requested engines, for any model requested twice.

    An engine whose checkpoint is missing falls back to generic whisper. If two
    requested engines both fall back, the comparison silently becomes one model
    against itself — identical output that reads like the models agreeing
    rather than like a broken test.
    """
    by_model: dict[str, list[str]] = {}
    for requested, model in resolved:
        by_model.setdefault(model, []).append(requested)
    return {model: names for model, names in by_model.items() if len(names) > 1}


def load_engines(names: list[str]) -> list:
    engines = []
    for name in names:
        try:
            # No fallback: we want to know an engine is genuinely unavailable
            # rather than silently comparing whisper against itself.
            engine = get_engine(name, allow_fallback=False)
        except Exception as exc:
            print(f"  skip {name:<14} {type(exc).__name__}: {exc}")
            continue
        started = time.perf_counter()
        try:
            engine.warm_up()
        except Exception as exc:
            print(f"  skip {name:<14} warm-up failed: {exc}")
            continue
        print(f"  ready {name:<13} {engine.name}  ({time.perf_counter()-started:.1f}s load)")
        engines.append((name, engine))
    return engines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="*", type=Path)
    ap.add_argument("--engines", default=DEFAULT_ENGINES,
                    help=f"comma-separated; available: {sorted(REGISTRY)}")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--catalogue", default="hawker")
    ap.add_argument("--no-bias", action="store_true",
                    help="disable catalogue biasing for all engines")
    args = ap.parse_args()

    clips = list(args.audio)
    if args.record:
        clip = record_clip(REPO / "data" / "eval" / "compare_clip.wav")
        if clip is None:
            return 2
        clips.insert(0, clip)
    if not clips:
        ap.error("give an audio file, or use --record")

    missing = [c for c in clips if not Path(c).exists()]
    if missing:
        print(f"no such file(s): {missing}")
        return 2

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        ap.error(f"unknown engine(s) {unknown}; choose from {sorted(REGISTRY)}")

    cat = load_catalogue(args.catalogue)
    print("Loading engines (first load downloads weights and is slow):")
    engines = load_engines(names)

    collisions = find_collisions([(n, e.name) for n, e in engines])
    if collisions:
        print("\n" + "=" * 74)
        print("COMPARISON INVALID — these engines resolved to the same model:")
        for model, requested in collisions.items():
            print(f"  {', '.join(requested)}  ->  {model}")
        print("\nAn engine falls back to generic whisper when its checkpoint is")
        print("missing, so you would be comparing one model against itself.")
        print("\nMost likely: the conversion has not succeeded yet. Run")
        print("  pip install torch && python scripts/convert_singlish.py")
        print("and check it prints 'Done.' before comparing again.")
        print("=" * 74)
        return 1

    if not engines:
        print("\nNo engines available on this machine. On Windows/Linux try:\n"
              "  python scripts/convert_singlish.py && "
              "python scripts/compare_engines.py --engines singlish <clip>")
        return 1

    for clip in clips:
        print(f"\n{'=' * 74}\n{Path(clip).name}\n{'=' * 74}")
        for name, engine in engines:
            bias = None if args.no_bias else cat.bias_text(engine.bias_style)
            try:
                result = engine.transcribe(str(clip), bias=bias)
            except Exception as exc:
                print(f"\n  {name:<14} ERROR {type(exc).__name__}: {exc}")
                continue
            _, matches = correct(result.text, cat)
            order = parse_order(result.text, cat, matches)
            print(f"\n  {name}  ({result.latency_ms}ms)")
            print(f"    heard : {result.text or '(nothing)'}")
            print(f"    order : {order.describe()}")

    print(f"\n{'=' * 74}")
    print("Read the 'heard' lines. If an engine drops or garbles the non-English\n"
          "words while others keep them, that engine cannot code-switch — which\n"
          "matters more than its score on English-only clips.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
