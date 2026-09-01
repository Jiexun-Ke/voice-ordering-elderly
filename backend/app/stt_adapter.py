"""
Adapter for the STT teammate's structured output.

Their service (`stt/parse.py` in voice-ordering-elderly) doesn't hand us plain
text — `POST /transcribe` already returns a partially structured order:

    {"order": {"lines": [{"canonical": "KOPI_C", "display": "Kopi-C",
                          "quantity": 2, "modifiers": ["siew dai"],
                          "price": 1.4}],
               "takeaway": true, "total": 2.8}}

This module maps that onto our menu so the dialogue layer can consume it
directly. Everything our side adds — clarification, the running tab,
confirmation, kitchen handoff — then works exactly as it does for raw text.

TWO MODELLING DIFFERENCES worth knowing:

1. They treat milk type as separate ITEMS (KOPI / KOPI_O / KOPI_C); we treat it
   as a modifier on one item. So the mapping carries the implied modifier.
2. Their `modifiers` list holds DISPLAY strings ("siew dai"), not canonical
   codes ("SIEW_DAI"), so both spellings are accepted here.

Raw-text input is unaffected: `DialogueManager.handle_utterance()` is untouched
and the standalone demo keeps working with no STT service running.
"""

# Their canonical -> (our item id, modifiers their item name implies)
CANONICAL_TO_MENU: dict[str, tuple[str, dict]] = {
    "KOPI":              ("kopi", {"milk_type": "condensed_milk"}),
    "KOPI_O":            ("kopi", {"milk_type": "black"}),
    "KOPI_C":            ("kopi", {"milk_type": "evaporated_milk"}),
    "TEH":               ("teh",  {"milk_type": "condensed_milk"}),
    "TEH_O":             ("teh",  {"milk_type": "black"}),
    "TEH_C":             ("teh",  {"milk_type": "evaporated_milk"}),
    "WANTON_MEE":        ("wonton_noodles", {}),
    "FISHBALL_NOODLES":  ("fishball_noodles", {}),
    "CHICKEN_RICE":      ("chicken_rice", {}),
    "NASI_LEMAK":        ("nasi_lemak", {}),
    "ROTI_PRATA":        ("roti_prata", {}),
    # Deliberately unmapped, because our menu has no equivalent: MILO,
    # KAYA_TOAST, HALF_BOILED_EGGS, CHAR_KWAY_TEOW, LAKSA, MEE_GORENG,
    # CARROT_CAKE, BEE_HOON. Also TAU_HUAY — the beancurd dessert is NOT the
    # same product as our Soya Bean Milk, so it is not silently equated.
    # These fall back to text matching, then to "not on the menu".
}

# Their modifier canonical OR display string -> (our group type, our option id)
MODIFIER_MAP: dict[str, tuple[str, str]] = {
    "siew_dai": ("sweetness", "less_sweet"),
    "siew dai": ("sweetness", "less_sweet"),
    "gah_dai": ("sweetness", "extra_sweet"),
    "gah dai": ("sweetness", "extra_sweet"),
    "kosong": ("sweetness", "no_sugar"),
    "gau": ("strength", "strong"),
    "gao": ("strength", "strong"),
    "po": ("strength", "weak"),
    "poh": ("strength", "weak"),
    "peng": ("temperature", "iced"),
    "iced": ("temperature", "iced"),
    "no_chilli": ("spice", "no_chilli"),
    "no chilli": ("spice", "no_chilli"),
    "extra_chilli": ("spice", "extra_chilli"),
    "extra chilli": ("spice", "extra_chilli"),
    "less_oil": (None, None),   # recognised, but we have no equivalent group
    "less oil": (None, None),
}

# Order-level in both systems, so it never becomes a line modifier.
TAKEAWAY_TOKENS = {"takeaway", "tapao", "dabao", "da bao"}


def map_modifiers(raw_modifiers, item) -> tuple[dict, bool]:
    """
    Turn their modifier list into our {group_type: option_id} dict.

    Returns (modifiers, takeaway_seen). Only groups the item actually has are
    kept, so a `spice` tag on a drink is dropped rather than invented.
    """
    valid_groups = {g.type.value for g in item.modifier_groups}
    mapped: dict[str, str] = {}
    takeaway_seen = False

    for raw in raw_modifiers or []:
        key = str(raw).strip().lower()
        if key in TAKEAWAY_TOKENS:
            takeaway_seen = True
            continue
        group_type, option_id = MODIFIER_MAP.get(key, (None, None))
        if group_type and group_type in valid_groups:
            mapped[group_type] = option_id
    return mapped, takeaway_seen


def option_name(item, group_type: str, option_id: str) -> str:
    for group in item.modifier_groups:
        if group.type.value != group_type:
            continue
        for opt in group.options:
            if opt.id == option_id:
                return opt.name
    return option_id
