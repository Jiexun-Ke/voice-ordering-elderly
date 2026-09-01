"""
Dummy in-store menu. This is the source of truth the speech transcript gets
matched against.

Each MenuItem's `aliases` list holds 2-3+ alternate ways an elderly customer
might say the item (dialect terms, generic terms, mispronunciations-as-text).
The canonical `name` is always matched too, so it doesn't need repeating in
`aliases`.

To add a new dish: add a MenuItem entry here. To make a dish require a choice
(like noodle type), attach one of the modifier-group builders below, or write
a new one following the same pattern.
"""
from .models import MenuItem, ModifierGroup, ModifierOption, ModifierType

# Whole-word category terms — if a customer says something generic like
# "I want noodles" with no specific dish name, we ask which dish in that
# category rather than guessing one via fuzzy match.
CATEGORY_ALIASES: dict[str, list[str]] = {
    "Noodles": ["noodle", "noodles", "mee"],
    "Rice": ["rice"],
    "Drinks": ["drink", "drinks", "beverage", "beverages"],
    "Snacks": ["snack", "snacks"],
}


def noodle_type_group(required: bool = True) -> ModifierGroup:
    return ModifierGroup(
        type=ModifierType.NOODLE_TYPE,
        prompt="Which type of noodle would you like - yellow noodle, kway teow, bee hoon, or instant noodle?",
        required=required,
        default="yellow_noodle",
        label="noodle",
        short_prompt="yellow noodle, kway teow, bee hoon, or instant noodle",
        options=[
            # No bare "mee" alias here: it's the generic Hokkien word for noodle
            # and appears inside dish names themselves ("wonton mee", "wan tan
            # mee"), so it would false-match the noodle-type choice. The generic
            # sense is covered by CATEGORY_ALIASES instead.
            ModifierOption("yellow_noodle", "Yellow Noodle", ["yellow noodle", "mee kuning", "egg noodle"]),
            ModifierOption("kway_teow", "Kway Teow", ["kway teow", "flat noodle", "hor fun"]),
            ModifierOption("bee_hoon", "Bee Hoon", ["bee hoon", "rice vermicelli", "thin noodle"]),
            ModifierOption("instant_noodle", "Instant Noodle", ["maggie noodle", "instant noodle", "maggi mee"]),
        ],
    )


def soup_style_group(required: bool = False) -> ModifierGroup:
    return ModifierGroup(
        type=ModifierType.SOUP_STYLE,
        prompt="Would you like it with soup, or dry?",
        required=required,
        default="soup",
        label="soup or dry",
        short_prompt="soup or dry",
        options=[
            ModifierOption("soup", "Soup", ["soup", "with soup", "wet"]),
            ModifierOption("dry", "Dry", ["dry", "no soup", "tossed", "without soup"]),
        ],
    )


def sweetness_group(required: bool = False) -> ModifierGroup:
    return ModifierGroup(
        type=ModifierType.SWEETNESS,
        prompt="How sweet would you like it - normal, siew dai, kosong, or gah dai?",
        required=required,
        default="normal",
        label="sweetness",
        short_prompt="normal, siew dai, or kosong",
        options=[
            # No bare "normal" alias: it collides with "normal strength" and
            # "normal chilli". A bare "normal" reply is handled by the
            # generic-default rule in the dialogue manager instead.
            ModifierOption("normal", "Normal Sweetness", ["normal sweet", "normal sweetness", "regular sweetness"]),
            ModifierOption(
                "less_sweet", "Siew Dai (Less Sweet)",
                ["less sweet", "siu dai", "siew dai", "sui dai", "not too sweet"],
            ),
            ModifierOption("no_sugar", "Kosong (No Sugar)", ["no sugar", "kosong", "unsweetened"]),
            ModifierOption(
                "extra_sweet", "Gah Dai (Extra Sweet)",
                ["extra sweet", "ga dai", "gah dai", "kah dai", "very sweet"],
            ),
        ],
    )


def milk_type_group(required: bool = False) -> ModifierGroup:
    """
    The base kopitiam drink-family choice: with condensed milk (the plain
    "kopi"/"teh"), with evaporated milk ("-C"), or black with no milk at all
    ("-O"). Combined with sweetness/strength/temperature below, this is what
    lets the menu cover every real kopi combination (Kopi-O Kosong Peng,
    Teh-C Siew Dai, ...) without hardcoding each one as a separate item.

    The `price_delta` values reproduce the STT teammate's catalogue pricing,
    where the milk variants are separately priced items (Kopi 1.20,
    Kopi-O 1.10, Kopi-C 1.40).
    """
    return ModifierGroup(
        type=ModifierType.MILK_TYPE,
        prompt="Would you like it with condensed milk, black with no milk (O), or with evaporated milk (C)?",
        required=required,
        default="condensed_milk",
        label="milk",
        short_prompt="normal with condensed milk, O for black, or C for evaporated milk",
        options=[
            ModifierOption(
                "condensed_milk", "With Condensed Milk",
                ["condensed milk", "with milk", "original"],
                price_delta=0.00,
            ),
            ModifierOption(
                "black", "Black, No Milk (O)",
                ["kopi o", "teh o", "kopi oh", "teh oh", "black no milk", "no milk", "black"],
                price_delta=-0.10,
            ),
            ModifierOption(
                "evaporated_milk", "With Evaporated Milk (C)",
                ["kopi c", "teh c", "kopi see", "teh see", "evaporated milk"],
                price_delta=0.20,
            ),
        ],
    )


def strength_group(required: bool = False) -> ModifierGroup:
    return ModifierGroup(
        type=ModifierType.STRENGTH,
        prompt="How strong would you like it - normal, gao for strong, or poh for weak?",
        required=required,
        default="normal",
        label="strength",
        short_prompt="normal, gao for strong, or poh for weak",
        options=[
            ModifierOption("normal", "Normal Strength", ["normal strength", "regular strength"]),
            ModifierOption("strong", "Gao (Strong)", ["strong", "gao", "kao", "kaw", "gau", "extra strong", "thick"]),
            ModifierOption("weak", "Poh (Weak)", ["weak", "poh", "po", "diluted", "light", "watery"]),
        ],
    )


def temperature_group(required: bool = False) -> ModifierGroup:
    return ModifierGroup(
        type=ModifierType.TEMPERATURE,
        prompt="Would you like it hot, or iced?",
        required=required,
        default="hot",
        label="temperature",
        short_prompt="hot or peng for iced",
        options=[
            ModifierOption("hot", "Hot", ["hot", "warm"]),
            ModifierOption("iced", "Iced (Peng)", ["iced", "ice", "peng", "cold"]),
        ],
    )


def spice_group(required: bool = True, default: str = "no_chilli") -> ModifierGroup:
    """
    Chilli level. Made a first-class choice because many elderly customers
    can't take spice at all, and several hawker dishes arrive with sambal or
    curry by default — so this is asked rather than assumed. The safe option
    is also the fallback: if the customer never answers, they get no chilli.
    """
    return ModifierGroup(
        type=ModifierType.SPICE,
        prompt="Would you like chilli - no chilli, a little, normal, or extra spicy?",
        required=required,
        default=default,
        label="chilli",
        short_prompt="no chilli, a little, or normal",
        options=[
            ModifierOption(
                "no_chilli", "No Chilli",
                ["no chilli", "no chili", "mai hiam", "not spicy", "no spicy",
                 "without chilli", "no sambal", "cannot take spicy", "dont want chilli"],
            ),
            ModifierOption(
                "less_chilli", "Less Chilli",
                ["less chilli", "less chili", "little bit chilli", "little chilli",
                 "small chilli", "not too spicy", "mild"],
            ),
            ModifierOption(
                "normal_chilli", "Normal Chilli",
                ["normal chilli", "normal chili", "regular chilli", "normal spicy", "with chilli"],
            ),
            ModifierOption(
                "extra_chilli", "Extra Chilli",
                ["extra chilli", "extra chili", "very spicy", "more chilli",
                 "extra spicy", "extra sambal", "super spicy"],
            ),
        ],
    )


# Prices: where an item also exists in the STT teammate's
# data/catalogues/hawker.json, THEIR price is used so the two halves of the
# system can never disagree on what a customer owes. Items with no equivalent
# on their side keep ours. See README for the reconciliation table.
MENU: list[MenuItem] = [
    MenuItem(
        "beef_noodles", "Beef Noodle Soup",
        ["beef noodle", "beef mee", "ngau lam mee"],
        "Noodles", 5.50,   # no equivalent in theirs
        # Chilli is a side condiment here, so it's offered but defaults to
        # none rather than being asked about — unlike the sambal/curry dishes
        # below, where spice is part of the dish and must be confirmed.
        [noodle_type_group(required=True), soup_style_group(), spice_group(required=False)],
    ),
    MenuItem(
        "fishball_noodles", "Fishball Noodles",
        ["fish ball noodle", "fishball noodle", "fishball mee", "yu wan mee"],
        "Noodles", 4.00,   # their FISHBALL_NOODLES
        [noodle_type_group(required=True), soup_style_group(), spice_group(required=False)],
    ),
    MenuItem(
        "wonton_noodles", "Wonton Noodles",
        ["wonton mee", "wan tan mee", "wanton noodles", "dumpling noodles"],
        "Noodles", 4.50,   # their WANTON_MEE
        [noodle_type_group(required=True), soup_style_group(), spice_group(required=False)],
    ),
    MenuItem(
        "chicken_rice", "Hainanese Chicken Rice",
        ["chicken rice", "chicken rice set", "kai fan"],
        "Rice", 4.50,   # their CHICKEN_RICE
        [spice_group(required=False)],
    ),
    MenuItem(
        "nasi_lemak", "Nasi Lemak",
        ["nasi lemak", "coconut rice", "nasi lemak set"],
        "Rice", 4.00,   # their NASI_LEMAK
        # Served with sambal by default — genuinely spicy, so always ask.
        [spice_group(required=True)],
    ),
    MenuItem(
        "fried_rice", "Egg Fried Rice",
        ["fried rice", "yeung chow fried rice", "egg fried rice"],
        "Rice", 4.80,   # no equivalent in theirs
        [spice_group(required=False)],
    ),
    MenuItem(
        "roti_prata", "Roti Prata",
        ["prata", "roti canai", "indian pancake"],
        "Snacks", 1.50,   # their ROTI_PRATA
        # Comes with curry dip — spice level is worth confirming.
        [spice_group(required=True)],
    ),
    MenuItem(
        "curry_puff", "Curry Puff",
        ["curry puff", "epok epok", "curry pastry"],
        "Snacks", 1.50,
        # Curry filling — ask, since some elderly can't take any spice.
        [spice_group(required=True)],
    ),
    # Kopi and Teh each carry the full kopitiam modifier system (milk type x
    # sweetness x strength x temperature) instead of being hardcoded as
    # separate items per combination — this is what lets "kopi-o kosong gao
    # peng" and "teh-c siew dai" both resolve correctly without needing a
    # menu entry for every one of the dozens of real combinations.
    MenuItem(
        "kopi", "Kopi (Traditional Coffee)",
        ["kopi", "coffee", "local coffee"],
        "Drinks", 1.20,   # their KOPI; -O is 1.10 and -C 1.40 via milk price_delta
        [milk_type_group(), sweetness_group(), strength_group(), temperature_group()],
    ),
    MenuItem(
        "teh", "Teh (Traditional Tea)",
        ["teh", "tea", "milk tea"],
        "Drinks", 1.20,   # their TEH; -O is 1.10 and -C 1.40 via milk price_delta
        [milk_type_group(), sweetness_group(), strength_group(), temperature_group()],
    ),
    MenuItem(
        "barley", "Barley Water",
        ["barley", "barley water", "barley drink", "iced barley"],
        "Drinks", 1.80,
        [temperature_group()],
    ),
    MenuItem(
        "soya_milk", "Soya Bean Milk",
        ["soya", "soya milk", "soy milk", "tau huay water", "beancurd drink"],
        # Deliberately NOT priced from their TAU_HUAY ($2.00) — that's the
        # beancurd dessert, a different product. Flagged for a team decision.
        "Drinks", 1.70,
        [temperature_group()],
    ),
]
