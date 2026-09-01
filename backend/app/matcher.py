"""
Turns raw transcript text into candidate menu items / modifier options.

Matching strategy, cheapest-first:
  1. Exact substring match against name + aliases (score 100, most confident).
  2. Fuzzy match (rapidfuzz token_set_ratio) against the same pool, for typos,
     word-order differences, or STT mishearings.

Returns are always `[(candidate, score), ...]` sorted best-first, so callers
can tell an unambiguous match (one clear winner) from an ambiguous one
(top two scores close together).
"""
import re

from rapidfuzz import fuzz, process

_PATTERN_CACHE: dict = {}

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "single": 1, "couple": 2, "few": 3,
}

_SPLIT_PATTERN = re.compile(r"\b(?:and|also|plus)\b|,", re.IGNORECASE)


def split_into_chunks(transcript: str) -> list[str]:
    """Break a multi-item utterance ('a beef noodle and a kopi') into pieces."""
    parts = [p.strip() for p in _SPLIT_PATTERN.split(transcript) if p.strip()]
    return parts or [transcript.strip()]


def extract_quantity(text: str) -> tuple[int, str]:
    """Pull a leading quantity out of a chunk, e.g. 'two beef noodles' -> (2, 'beef noodles')."""
    tokens = text.split()
    for i, tok in enumerate(tokens):
        clean = tok.strip(",.!?").lower()
        if clean.isdigit():
            remaining = " ".join(tokens[:i] + tokens[i + 1:])
            return int(clean), remaining
        if clean in NUMBER_WORDS:
            remaining = " ".join(tokens[:i] + tokens[i + 1:])
            return NUMBER_WORDS[clean], remaining
    return 1, text


def _normalize(text: str) -> str:
    """
    Lowercase and turn hyphens into spaces. Written Singlish commonly
    hyphenates compound drink terms ("kopi-o", "teh-c") even though our
    aliases are stored space-separated ("kopi o") — without this, an exact
    substring match on a hyphenated form would silently miss.
    """
    return text.lower().replace("-", " ")


def _plural_variants(form: str) -> list[str]:
    """
    Both "fishball noodle" and "Fishball Noodles" should match each other.
    Elderly speech (and Singlish generally) drops plural -s freely, so every
    alias is registered in both forms rather than relying on fuzzy matching
    to bridge a one-character difference.
    """
    variants = [form]
    if form.endswith("s"):
        variants.append(form[:-1])
    else:
        variants.append(form + "s")
    return variants


def _phrase_pattern(form: str):
    """Compiled whole-word matcher for an alias, cached across calls."""
    pat = _PATTERN_CACHE.get(form)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(form)}\b")
        _PATTERN_CACHE[form] = pat
    return pat


def _contains_phrase(text: str, form: str) -> bool:
    """
    Whole-word containment, NOT raw substring. Short aliases hide inside
    ordinary words — "tea" sits inside "ins-tea-d", "any" inside "company",
    "ice" inside "nice" — and a bare substring test turns those into phantom
    orders. Matching on word boundaries is what keeps short dialect aliases
    (mee, teh, kopi, gao) safe to include.
    """
    return bool(_phrase_pattern(form).search(text))


def _alias_pool(candidates, name_attr="name", alias_attr="aliases"):
    """Map every lowercase name/alias string -> the candidate object it belongs to."""
    pool = {}
    for c in candidates:
        forms = [getattr(c, name_attr).lower()] + [a.lower() for a in getattr(c, alias_attr)]
        for f in forms:
            for variant in _plural_variants(_normalize(f)):
                pool.setdefault(variant, c)
    return pool


def _match_generic(text: str, candidates, id_attr="id", threshold=75, fuzzy=True):
    """Shared matching logic for both MenuItems and ModifierOptions."""
    if not candidates:
        return []
    pool = _alias_pool(candidates)
    text_l = _normalize(text)

    exact_hits = {}
    for form, cand in pool.items():
        if form and _contains_phrase(text_l, form):
            cid = getattr(cand, id_attr)
            if cid not in exact_hits or len(form) > len(exact_hits[cid][1]):
                exact_hits[cid] = (cand, form)
    if exact_hits:
        return sorted(
            [(cand, 100) for cand, _ in exact_hits.values()],
            key=lambda x: -len(getattr(x[0], id_attr)),
        )
    if not fuzzy:
        return []

    results = process.extract(text_l, list(pool.keys()), scorer=fuzz.token_set_ratio, limit=5)
    matched = {}
    for choice, score, _ in results:
        if score >= threshold:
            cand = pool[choice]
            cid = getattr(cand, id_attr)
            if cid not in matched or score > matched[cid][1]:
                matched[cid] = (cand, score)
    return sorted(matched.values(), key=lambda x: -x[1])


def match_item(text: str, menu, threshold: int = 75, fuzzy: bool = True):
    """Match a chunk of text against a list of MenuItem. Returns [(MenuItem, score), ...]."""
    return _match_generic(text, menu, id_attr="id", threshold=threshold, fuzzy=fuzzy)


def match_options(text: str, options, threshold: int = 75, fuzzy: bool = True):
    """Match text against a list of ModifierOption. Returns [(ModifierOption, score), ...]."""
    return _match_generic(text, options, id_attr="id", threshold=threshold, fuzzy=fuzzy)


def match_category(text: str, menu, category_aliases: dict) -> list:
    """
    Whole-word match against category names (e.g. 'noodle(s)' -> Noodles).
    Used as a middle ground between an exact dish match and a blind fuzzy
    guess: a bare category word is genuinely ambiguous and should prompt a
    "which one?" question rather than being silently resolved to whichever
    dish happens to score highest by coincidence.
    """
    text_l = _normalize(text)
    for category, keywords in category_aliases.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text_l):
                return [item for item in menu if item.category == category]
    return []


def match_modifier_option(text: str, modifier_group, threshold: int = 75):
    return match_options(text, modifier_group.options, threshold)


def strip_matched_form(text: str, item) -> str:
    """
    Remove the substring of `text` that matched `item`'s name/alias, so the
    leftover text can be safely scanned for modifiers without the item's own
    name (e.g. the word "noodle" in "beef noodle") being mistaken for a
    modifier keyword (e.g. matching the "noodle_type" option "egg noodle").
    """
    text_l = _normalize(text)
    forms = sorted([item.name] + item.aliases, key=len, reverse=True)
    for form in forms:
        # Whole-word only, for the same reason as _contains_phrase.
        m = _phrase_pattern(_normalize(form)).search(text_l)
        if m:
            return (text[:m.start()] + " " + text[m.end():]).strip()
    return text
