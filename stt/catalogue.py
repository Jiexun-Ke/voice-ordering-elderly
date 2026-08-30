"""Merchant catalogue: the biasing prompt and the correction vocabulary.

One source of truth feeding two different accuracy mechanisms:

  1. BEFORE transcription — a biasing string that tilts the model toward these
     words. voice_ordering.py calls this "the single most important knob in
     this whole script" and it is right.
  2. AFTER transcription — the canonical term list correct.py fuzzy-matches
     against, which catches what biasing missed.

Because both read the same JSON, curating a catalogue improves both paths at
once. That makes catalogue curation the highest accuracy-per-hour task in the
project, and it needs no Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Both Whisper and Qwen3-ASR degrade when the biasing prompt grows too long;
# voice_ordering.py's comment puts the limit at ~200 tokens. We estimate
# conservatively at 4 characters per token rather than taking a tokenizer
# dependency for a budget that only needs to be roughly right.
MAX_BIAS_TOKENS = 200
CHARS_PER_TOKEN = 4


@dataclass
class Entry:
    """One orderable thing, or one modifier applied to one."""

    canonical: str
    display: str
    aliases: list[str] = field(default_factory=list)
    price: float | None = None
    kind: str = "item"  # "item" | "modifier"

    def surface_forms(self) -> list[str]:
        """Every way this might be said or transcribed, display name first."""
        seen, out = set(), []
        for form in [self.display, *self.aliases]:
            key = form.lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(form)
        return out


class Catalogue:
    def __init__(self, merchant: str, entries: list[Entry], merchant_id: str = ""):
        self.merchant = merchant
        self.merchant_id = merchant_id or merchant.lower().replace(" ", "_")
        self.entries = entries

    # ---------- loading ----------

    @classmethod
    def from_dict(cls, data: dict) -> "Catalogue":
        entries: list[Entry] = []
        for kind in ("items", "modifiers"):
            for raw in data.get(kind, []):
                entries.append(
                    Entry(
                        canonical=raw["canonical"],
                        display=raw.get("display", raw["canonical"]),
                        aliases=list(raw.get("aliases", [])),
                        price=raw.get("price"),
                        kind="item" if kind == "items" else "modifier",
                    )
                )
        return cls(
            merchant=data.get("merchant", "Unknown"),
            merchant_id=data.get("id", ""),
            entries=entries,
        )

    @classmethod
    def load(cls, path: str | Path) -> "Catalogue":
        return cls.from_dict(json.loads(Path(path).read_text()))

    # ---------- views ----------

    @property
    def items(self) -> list[Entry]:
        return [e for e in self.entries if e.kind == "item"]

    @property
    def modifiers(self) -> list[Entry]:
        return [e for e in self.entries if e.kind == "modifier"]

    def lookup(self, surface: str) -> Entry | None:
        """Exact (case-insensitive) match of a spoken form to an entry."""
        needle = surface.lower().strip()
        for entry in self.entries:
            if any(f.lower() == needle for f in entry.surface_forms()):
                return entry
        return None

    def all_surface_forms(self) -> dict[str, Entry]:
        """Every surface form mapped to its entry, for fuzzy matching."""
        table: dict[str, Entry] = {}
        for entry in self.entries:
            for form in entry.surface_forms():
                table.setdefault(form.lower(), entry)
        return table

    # ---------- biasing ----------

    def bias_text(self, style: str = "sentence") -> str:
        """Build the biasing string, truncated to the token budget.

        Display names for every entry go in first, then aliases, so a long
        catalogue degrades by dropping synonyms rather than by dropping whole
        products. Qwen3-ASR is sensitive to the framing words: "Vocabulary:"
        and "Proper nouns:" measurably outperform "Terms:" or "Context:", so
        the two styles are not cosmetic.
        """
        prefix = "Vocabulary: " if style == "vocabulary" else "Food order. Items: "
        budget = MAX_BIAS_TOKENS * CHARS_PER_TOKEN - len(prefix)

        chosen: list[str] = []
        used = 0
        # Pass 1: display names. Pass 2: aliases.
        for forms in (
            [e.display for e in self.entries],
            [a for e in self.entries for a in e.aliases],
        ):
            for form in forms:
                form = form.strip()
                if not form or form in chosen:
                    continue
                cost = len(form) + 2  # ", "
                if used + cost > budget:
                    return prefix + ", ".join(chosen) + "."
                chosen.append(form)
                used += cost

        return prefix + ", ".join(chosen) + "."


def load_catalogue(name_or_path: str | Path) -> Catalogue:
    """Load by file path, or by bare name from data/catalogues/."""
    path = Path(name_or_path)
    if not path.exists() and path.suffix != ".json":
        path = Path(__file__).resolve().parents[1] / "data" / "catalogues" / f"{name_or_path}.json"
    return Catalogue.load(path)
