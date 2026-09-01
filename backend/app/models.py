"""
Shared data structures for the order-matching service.

Nothing in this file talks to speech-to-text or the kitchen directly —
it's just the vocabulary the rest of the app is built on.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModifierType(str, Enum):
    NOODLE_TYPE = "noodle_type"
    SOUP_STYLE = "soup_style"
    SWEETNESS = "sweetness"
    MILK_TYPE = "milk_type"
    STRENGTH = "strength"
    TEMPERATURE = "temperature"
    SPICE = "spice"


@dataclass
class ModifierOption:
    id: str
    name: str
    aliases: list[str]
    # Some choices change the price: a Kopi-C costs more than a Kopi-O even
    # though both are the same base item. Added to the item price per unit.
    price_delta: float = 0.0


@dataclass
class ModifierGroup:
    type: ModifierType
    prompt: str                 # spoken question if this is the only thing missing
    required: bool               # must the elderly specify this? (e.g. noodle type)
    default: Optional[str]       # option id used when not required and unspecified
    options: list[ModifierOption]
    # Used when several required choices are missing at once and we ask for
    # them in a single breath instead of one question per turn:
    #   label        -> "sweetness"
    #   short_prompt -> "normal, siew dai, or kosong"
    label: str = ""
    short_prompt: str = ""


@dataclass
class MenuItem:
    id: str
    name: str
    aliases: list[str]           # 2-3+ alternate ways of saying this item (name is implicit)
    category: str
    price: float
    modifier_groups: list[ModifierGroup] = field(default_factory=list)


@dataclass
class OrderLine:
    line_id: str
    item_id: str
    item_name: str
    quantity: int
    unit_price: float
    modifiers: dict = field(default_factory=dict)         # modifier_type -> option_id
    modifier_names: dict = field(default_factory=dict)    # modifier_type -> option name (for speech/display)
    sent: bool = False                    # already handed to the kitchen?
    kitchen_status: Optional[str] = None  # received | preparing | done

    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class Order:
    order_id: str
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "in_progress"           # in_progress | sent_to_kitchen | paid
    takeaway: Optional[bool] = None       # None = not stated yet
    paid_at: Optional[str] = None         # ISO timestamp, set when the bill is settled

    @property
    def new_lines(self) -> list:
        """Lines not yet sent to the kitchen — the only ones a confirm should send."""
        return [l for l in self.lines if not l.sent]

    @property
    def total(self) -> float:
        return round(sum(l.subtotal for l in self.lines), 2)


@dataclass
class DraftLine:
    """An order line that's still being built while we resolve missing info."""
    item_id: Optional[str]
    item_name: Optional[str]
    quantity: int
    modifiers: dict = field(default_factory=dict)
    modifier_names: dict = field(default_factory=dict)
    # Groups filled in from a default rather than stated by the customer.
    # Overwriting one of these is them answering, not correcting themselves,
    # so it shouldn't be read back as "changed to ...".
    defaulted: set = field(default_factory=set)


@dataclass
class PendingClarification:
    """
    What the system is currently waiting to hear back about.
    Exactly one of these lives on a Session at a time.
    """
    kind: str                    # item_ambiguous | modifier_missing | modifier_ambiguous
                                  # | modifier_batch | confirm_item | remove_ambiguous
                                  # | change_ambiguous | change_item_target
                                  # | takeaway_choice | confirm_payment
    question: str
    item_candidates: list = field(default_factory=list)        # list[MenuItem]
    modifier_group: Optional[ModifierGroup] = None
    modifier_candidates: list = field(default_factory=list)    # list[ModifierOption]
    modifier_groups: list = field(default_factory=list)        # list[ModifierGroup], for modifier_batch
    draft: Optional[DraftLine] = None
    target_line_id: list = field(default_factory=list)         # OrderLine.line_id values in play
    retries: int = 0


@dataclass
class Session:
    """
    One table's ordering conversation. Lives from the customer sitting down
    until the bill is paid, spanning as many rounds of ordering as they like.
    """
    session_id: str
    order: Order
    table_id: str = ""
    pending: Optional[PendingClarification] = None
    chunk_queue: list = field(default_factory=list)   # transcript fragments still waiting to be processed
    history: list = field(default_factory=list)       # raw transcripts, for debugging/logging


@dataclass
class DialogueResponse:
    """What the dialogue manager hands back after each transcript turn."""
    message: str                       # text to be spoken back to the elderly (TTS is teammate's side)
    needs_clarification: bool
    order_confirmed: bool = False
    order_snapshot: Optional[dict] = None
    kitchen_response: Optional[dict] = None
    receipt: Optional[dict] = None      # set only when the bill has just been paid
