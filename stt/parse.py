"""Corrected transcript -> structured order JSON for the backend.

Association rules, chosen because they match how people actually order rather
than what is easiest to implement:

  * A quantity binds to the item that FOLLOWS it ("two kopi").
  * A modifier binds to the item that PRECEDES it ("kopi c siew dai"), since
    Singlish modifiers are postfix. A modifier appearing before any item binds
    to the first item instead.
  * Takeaway is treated as order-level, not per-item — "tapao" at the end of a
    three-item order almost always means the whole order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalogue import Catalogue
from .correct import Match, correct, normalize

# Quantity words across the languages an elderly Singaporean diner may mix.
# Kept as data rather than a regex so a teammate can extend it without
# understanding the parser.
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    # Malay
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    # Mandarin / Hokkien romanisations
    "yi": 1, "er": 2, "liang": 2, "san": 3, "si": 4, "wu": 5,
    "yat": 1, "nng": 2, "sann": 3,
}

# Modifiers that describe the whole order rather than one line.
ORDER_LEVEL = {"TAKEAWAY"}


@dataclass
class OrderLine:
    canonical: str
    display: str
    quantity: int = 1
    modifiers: list[str] = field(default_factory=list)
    price: float | None = None

    def to_dict(self) -> dict:
        return {
            "canonical": self.canonical,
            "display": self.display,
            "quantity": self.quantity,
            "modifiers": self.modifiers,
            "price": self.price,
        }


@dataclass
class Order:
    lines: list[OrderLine] = field(default_factory=list)
    takeaway: bool = False

    @property
    def total(self) -> float | None:
        """None if the order is empty or any line has no price."""
        if not self.lines:
            return None
        subtotal = 0.0
        for line in self.lines:
            if line.price is None:
                return None
            subtotal += line.price * line.quantity
        return round(subtotal, 2)

    def to_dict(self) -> dict:
        return {
            "lines": [line.to_dict() for line in self.lines],
            "takeaway": self.takeaway,
            "total": self.total,
        }

    def describe(self) -> str:
        """Human-readable readback for the confirmation step.

        This string is what an elderly diner hears or reads back, so it uses
        display names and plain quantities rather than canonical codes.
        """
        if not self.lines:
            return "nothing recognised"
        parts = []
        for line in self.lines:
            text = f"{line.quantity}x {line.display}"
            if line.modifiers:
                text += " (" + ", ".join(line.modifiers) + ")"
            parts.append(text)
        summary = ", ".join(parts)
        return summary + (" — takeaway" if self.takeaway else "")


def _quantity_before(tokens: list[str], index: int) -> int:
    """Look one token back for a number word or digit."""
    if index <= 0:
        return 1
    token = tokens[index - 1]
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    if token.isdigit():
        return max(1, int(token))
    return 1


def parse_order(text: str, catalogue: Catalogue,
                matches: list[Match] | None = None) -> Order:
    """Build an Order from a transcript (running correction if needed)."""
    if matches is None:
        _, matches = correct(text, catalogue)

    tokens = normalize(text).split()
    prices = {e.canonical: e.price for e in catalogue.entries}

    order = Order()
    pending_modifiers: list[str] = []

    for match in matches:
        if match.kind == "modifier":
            if match.canonical in ORDER_LEVEL:
                order.takeaway = True
            elif order.lines:
                # Postfix modifier: attach to the most recent line.
                if match.display not in order.lines[-1].modifiers:
                    order.lines[-1].modifiers.append(match.display)
            else:
                # Spoken before any item; hold it for the first one.
                pending_modifiers.append(match.display)
            continue

        line = OrderLine(
            canonical=match.canonical,
            display=match.display,
            quantity=_quantity_before(tokens, match.start),
            modifiers=list(pending_modifiers),
            price=prices.get(match.canonical),
        )
        pending_modifiers.clear()
        order.lines.append(line)

    return order
