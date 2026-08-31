"""Post-ASR correction: transcript spans -> canonical catalogue terms.

This is where menu accuracy is actually won. Biasing tilts the model before it
decodes; this catches what still came out wrong afterwards. The two compound,
and unlike biasing this works identically on every engine — including any that
exposes no biasing hook at all.

Worked example: Whisper hears "char kuey teow", which is not a catalogue
surface form. Fuzzy matching maps it to CHAR_KWAY_TEOW at ~0.92 similarity,
and the order is right.
"""


import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .catalogue import Catalogue, Entry

# Below this similarity, matches are more often wrong than right. Tuned to be
# forgiving of ASR spelling drift ("kuey"/"kway") while rejecting unrelated
# words. Day 6 should re-tune this against the recorded test set.
DEFAULT_THRESHOLD = 82.0

# Longest catalogue term is 3 words ("char kway teow"), but allow headroom for
# aliases like "hainanese chicken rice".
MAX_NGRAM = 4

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Light normalization so matching sees words, not punctuation.

    Mirrors the approach in voice_ordering.py's normalize() so that eval
    numbers computed here stay comparable with the prototype's.
    """
    return _SPACE.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


@dataclass
class Match:
    term: str          # what the transcript actually said
    canonical: str     # what it maps to
    display: str
    kind: str          # "item" | "modifier"
    score: float       # 0-100
    start: int         # token index, inclusive
    end: int           # token index, exclusive

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "canonical": self.canonical,
            "display": self.display,
            "kind": self.kind,
            "score": round(self.score / 100, 3),
        }


def find_matches(text: str, catalogue: Catalogue,
                 threshold: float = DEFAULT_THRESHOLD) -> list[Match]:
    """Greedy non-overlapping fuzzy match of transcript spans to catalogue.

    Scores every n-gram against every surface form, then takes the best
    matches first and drops any that overlap an already-taken span. Longer
    matches win ties, so "kopi c" is preferred over a bare "kopi".
    """
    tokens = normalize(text).split()
    if not tokens:
        return []

    surface_forms = catalogue.all_surface_forms()
    candidates: list[Match] = []

    for size in range(1, min(MAX_NGRAM, len(tokens)) + 1):
        for start in range(len(tokens) - size + 1):
            span = " ".join(tokens[start:start + size])
            best_form, best_score = None, 0.0
            for form in surface_forms:
                score = fuzz.ratio(span, form)
                if score > best_score:
                    best_form, best_score = form, score
            if best_form is not None and best_score >= threshold:
                entry: Entry = surface_forms[best_form]
                candidates.append(
                    Match(
                        term=span,
                        canonical=entry.canonical,
                        display=entry.display,
                        kind=entry.kind,
                        score=best_score,
                        start=start,
                        end=start + size,
                    )
                )

    # Best score first; longer spans break ties so multi-word terms beat their
    # own prefixes.
    candidates.sort(key=lambda m: (m.score, m.end - m.start), reverse=True)

    taken: set[int] = set()
    chosen: list[Match] = []
    for match in candidates:
        positions = set(range(match.start, match.end))
        if positions & taken:
            continue
        taken |= positions
        chosen.append(match)

    return sorted(chosen, key=lambda m: m.start)


def correct(text: str, catalogue: Catalogue,
            threshold: float = DEFAULT_THRESHOLD) -> tuple[str, list[Match]]:
    """Return (transcript with catalogue terms canonicalised, matches).

    The rewritten text is for humans to read back; `matches` is what parse.py
    and the backend should actually consume.
    """
    matches = find_matches(text, catalogue, threshold)
    if not matches:
        return normalize(text), []

    tokens = normalize(text).split()
    out: list[str] = []
    cursor = 0
    for match in matches:
        out.extend(tokens[cursor:match.start])
        out.append(match.display)
        cursor = match.end
    out.extend(tokens[cursor:])
    return " ".join(out), matches
