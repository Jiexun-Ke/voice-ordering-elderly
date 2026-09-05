"""Backend-authoritative stock checks for draft cart mutations."""

from dataclasses import dataclass

from .kitchen_interface import check_availability


@dataclass(frozen=True)
class StockConflict:
    """A machine-readable stock conflict for an unconfirmed cart change."""

    item_id: str
    requested_quantity: int
    available_quantity: int

    @property
    def detail(self) -> dict:
        return {
            "code": "stock_unavailable",
            "message": (
                f"Not enough stock for {self.item_id}: requested "
                f"{self.requested_quantity}, but only "
                f"{self.available_quantity} available."
            ),
            "item_id": self.item_id,
            "requested_quantity": self.requested_quantity,
            "available_quantity": self.available_quantity,
        }


def _draft_quantity(order, item_id: str, exclude_line_id: str | None = None) -> int:
    """Return the quantity already requested by unsent lines for an item."""
    return sum(
        line.quantity
        for line in order.lines
        if not line.sent
        and line.item_id == item_id
        and line.line_id != exclude_line_id
    )


def check_draft_availability(
    order, item_id: str, quantity: int, exclude_line_id: str | None = None
) -> StockConflict | None:
    """Check a candidate draft quantity against stock and other draft lines.

    Draft carts do not reserve inventory, so the kitchen's current stock is
    read without decrementing it. Already-sent lines are excluded because
    their quantities were accepted and deducted during confirmation.
    """
    requested_quantity = _draft_quantity(order, item_id, exclude_line_id) + quantity
    availability = check_availability(item_id, requested_quantity)
    if availability["available"]:
        return None
    return StockConflict(
        item_id=item_id,
        requested_quantity=requested_quantity,
        available_quantity=availability["remaining_stock"],
    )


def check_draft_line(order, line, exclude_line_id: str | None = None) -> StockConflict | None:
    """Check an ``OrderLine`` candidate using the shared draft rules."""
    return check_draft_availability(
        order,
        line.item_id,
        line.quantity,
        exclude_line_id=exclude_line_id,
    )
