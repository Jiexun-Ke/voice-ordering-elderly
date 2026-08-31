"""Bake-off harness: engines x biasing, by WER and latency.

Extends the idea in voice_ordering.py's run_eval() — which compared biased vs
unbiased decoding on one engine — to compare several engines at once, and to
break out a dialect subset separately.

The dialect column is the interesting one. Polyglot-Lion was fine-tuned on
English, Mandarin, Malay and Tamil only, while its base model (Qwen3-ASR)
advertises Cantonese and Minnan. Whether that ability survived fine-tuning is
unpublished, so this table answers a genuinely open question — worth a slide.

Usage:
    python -m stt.eval data/eval
    python -m stt.eval data/eval --engines polyglot,qwen,whisper
    python -m stt.eval data/eval --catalogue grocery

refs.csv columns: filename,reference[,tag]
`tag` is free-form (e.g. "dialect", "elderly", "codeswitch"); any row tagged
is reported as its own subset as well as in the overall figure.
"""

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from .catalogue import load_catalogue
from .correct import correct, normalize
from .engines import REGISTRY, get_engine


def _wer(refs: list[str], hyps: list[str]) -> float:
    from jiwer import wer

    return wer(refs, hyps)


def _load_rows(folder: Path) -> list[dict]:
    refs = folder / "refs.csv"
    if not refs.exists():
        sys.exit(
            f"no refs.csv in {folder}.\n"
            "Create one with columns: filename,reference[,tag]\n"
            "This is the Day 3 gate — without recorded audio no model question "
            "is answerable."
        )
    with open(refs) as fh:
        # Teammates annotate these files, so tolerate # comments and blank
        # lines rather than trying to open "# Day 3 gate..." as a wav.
        lines = [
            ln for ln in fh
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
    rows = [r for r in csv.DictReader(lines) if (r.get("filename") or "").strip()]
    if not rows:
        sys.exit(f"{refs} has a header but no data rows yet (Day 3 gate).")
    return rows


def run(folder: Path, engine_names: list[str], catalogue_name: str,
        threshold_report: bool = True) -> dict:
    rows = _load_rows(folder)
    cat = load_catalogue(catalogue_name)

    results: dict[tuple[str, bool], dict] = {}

    for engine_name in engine_names:
        try:
            engine = get_engine(engine_name, allow_fallback=False)
            engine.warm_up()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skipping {engine_name}: {type(exc).__name__}: {exc}")
            continue

        for use_bias in (True, False):
            bias = cat.bias_text(engine.bias_style) if use_bias else None
            refs, hyps, latencies = [], [], []
            by_tag: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
            corrected_hyps = []

            for row in rows:
                wav = folder / row["filename"]
                if not wav.exists():
                    print(f"  ! missing {wav}")
                    continue
                result = engine.transcribe(str(wav), bias=bias)
                reference = normalize(row["reference"])
                hypothesis = normalize(result.text)
                corrected, _ = correct(result.text, cat)

                refs.append(reference)
                hyps.append(hypothesis)
                corrected_hyps.append(normalize(corrected))
                latencies.append(result.latency_ms)

                tag = (row.get("tag") or "").strip()
                if tag:
                    by_tag[tag][0].append(reference)
                    by_tag[tag][1].append(hypothesis)

            if not refs:
                continue

            results[(engine.name, use_bias)] = {
                "wer": _wer(refs, hyps),
                # WER after fuzzy correction: the number that reflects what the
                # backend actually receives, and usually the more honest one.
                "wer_corrected": _wer(refs, corrected_hyps),
                "n": len(refs),
                "p50_ms": int(statistics.median(latencies)),
                "p95_ms": int(
                    statistics.quantiles(latencies, n=20)[-1]
                    if len(latencies) > 1 else latencies[0]
                ),
                "by_tag": {t: _wer(r, h) for t, (r, h) in by_tag.items()},
            }

    _print_table(results)
    return results


def _print_table(results: dict) -> None:
    if not results:
        print("\nNo results — every engine failed to load, or no audio matched.")
        return

    print(f"\n{'engine':<28} {'bias':<6} {'WER':>7} {'WER+fix':>8} "
          f"{'p50':>7} {'p95':>7} {'n':>4}")
    print("-" * 72)
    for (engine, bias), r in sorted(results.items()):
        print(f"{engine:<28} {'on' if bias else 'off':<6} "
              f"{r['wer']:>7.3f} {r['wer_corrected']:>8.3f} "
              f"{r['p50_ms']:>6}ms {r['p95_ms']:>6}ms {r['n']:>4}")

    tags = sorted({t for r in results.values() for t in r["by_tag"]})
    if tags:
        print(f"\n{'engine':<28} {'bias':<6} " + " ".join(f"{t:>10}" for t in tags))
        print("-" * 72)
        for (engine, bias), r in sorted(results.items()):
            cells = " ".join(
                f"{r['by_tag'].get(t, float('nan')):>10.3f}" for t in tags
            )
            print(f"{engine:<28} {'on' if bias else 'off':<6} {cells}")

    print("\nWER+fix is after fuzzy correction — the number the backend sees.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path, help="folder containing refs.csv and wavs")
    ap.add_argument("--engines", default="polyglot,whisper",
                    help=f"comma-separated; choose from {sorted(REGISTRY)}")
    ap.add_argument("--catalogue", default="hawker")
    args = ap.parse_args()

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        sys.exit(f"unknown engine(s): {unknown}; choose from {sorted(REGISTRY)}")

    run(args.folder, names, args.catalogue)


if __name__ == "__main__":
    main()
