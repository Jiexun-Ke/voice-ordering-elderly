"""
Contract boundary with the kitchen module (owned by a teammate).

This file is deliberately the ONLY place that "talks to the kitchen."
Everything above this line (matching, dialogue state) only ever deals with
Order/OrderLine objects and never needs to know how the kitchen is actually
reached.

--------------------------------------------------------------------------
CONTRACT

1) send_order_to_kitchen(order, lines=None) — what we send:
{
  "order_id": "b3f1...",
  "lines": [
    {
      "line_id": "b7e2...",
      "item_id": "beef_noodles",
      "name": "Beef Noodle Soup",
      "quantity": 2,
      "modifiers": {"noodle_type": "kway_teow", "soup_style": "soup"},
      "unit_price": 5.5
    }
  ]
}

`lines` limits the send to specific OrderLines. A table keeps a running tab,
so a second round must only send the NEW lines — never re-send what the
kitchen already has.

What we expect back:
{
  "order_id": "b3f1...",
  "accepted": true,            # false if ANY line was unavailable
  "line_results": [
    {
      "line_id": "b7e2...",    # echo it back: names are not unique per line
      "item_id": "beef_noodles",
      "name": "Beef Noodle Soup",
      "requested_quantity": 2,
      "available": true,
      "remaining_stock": 13,
      "status": "received"     # received | preparing | done
    }
  ]
}

2) ORDER STATUS + CANCELLATION

Every accepted line moves through:  received -> preparing -> done

    get_line_status(order_id, line_id) -> str | None
    cancel_line(order_id, line_id)     -> {"cancelled": bool, "status": str, "reason": str}

A line can only be cancelled while it is still "received". Once the kitchen
has started cooking ("preparing") or finished ("done"), cancellation is
refused — the food already exists and someone has to pay for it.

TO INTEGRATE THE REAL KITCHEN SERVICE: replace the bodies of
send_order_to_kitchen(), get_line_status() and cancel_line() with real calls
(direct import, REST POST, or an AWS SQS send_message) speaking this same
JSON shape. Nothing else in this codebase needs to change.
--------------------------------------------------------------------------
"""
from .models import KitchenStatus, Order, next_kitchen_status, serialize_kitchen_status

# Dummy stock levels, standing in for the kitchen's real inventory store.
_DEFAULT_STOCK = {
    "beef_noodles": 15, "fishball_noodles": 20, "wonton_noodles": 18,
    "chicken_rice": 25, "nasi_lemak": 20, "fried_rice": 22,
    "roti_prata": 30, "curry_puff": 40,
    "kopi": 50, "teh": 50, "barley": 30, "soya_milk": 30,
}
_STOCK = dict(_DEFAULT_STOCK)

# line_id -> status, standing in for the kitchen's ticket board.
_LINE_STATUS: dict[str, KitchenStatus] = {}
# line_id -> (order_id, item_id, accepted_quantity), used for exact restoration.
_LINE_TICKETS: dict[str, tuple[str, str, int]] = {}
# A cancelled ticket remains recorded so a repeated cancellation is idempotent.
_CANCELLED_LINES: set[tuple[str, str]] = set()

STATUS_FLOW = [
    KitchenStatus.ORDER_RECEIVED,
    KitchenStatus.IN_PREPARATION,
    KitchenStatus.DONE,
]


def order_to_kitchen_payload(order: Order, lines=None) -> dict:
    """`lines` defaults to every line; pass order.new_lines to send only new ones."""
    selected = order.lines if lines is None else lines
    return {
        "order_id": order.order_id,
        "lines": [
            {
                "line_id": line.line_id,
                "item_id": line.item_id,
                "name": line.item_name,
                "quantity": line.quantity,
                "modifiers": line.modifiers,
                "unit_price": line.unit_price,
            }
            for line in selected
        ],
    }


def get_stock_status(item_id: str) -> int:
    """Return current stock for an item; unknown menu items have zero stock."""
    return _STOCK.get(item_id, 0)


def get_all_stock() -> dict[str, int]:
    """Return a copy of the current stock table."""
    return dict(_STOCK)


def _validate_quantity(quantity: int) -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
        raise ValueError("quantity must be a non-negative integer")
    return quantity


def check_availability(item_id: str, quantity: int) -> dict:
    """Check stock without changing it.

    ``remaining_stock`` is the current quantity, including when the request
    cannot be fulfilled. Unknown item IDs are unavailable even for a zero
    quantity request.
    """
    quantity = _validate_quantity(quantity)
    remaining_stock = get_stock_status(item_id)
    return {
        "item_id": item_id,
        "requested_quantity": quantity,
        "available": item_id in _STOCK and remaining_stock >= quantity,
        "remaining_stock": remaining_stock,
    }


def send_order_to_kitchen(order: Order, lines=None) -> dict:
    """
    MOCK implementation standing in for the teammate's kitchen module.
    Simulates the kitchen checking + decrementing stock so the rest of the
    system can be built and demoed end-to-end before the real integration
    exists.
    """
    payload = order_to_kitchen_payload(order, lines)
    line_results = []
    all_available = True
    for line in payload["lines"]:
        line_id = line["line_id"]
        ticket = _LINE_TICKETS.get(line_id)
        if ticket is not None and ticket[0] == payload["order_id"] and line_id in _LINE_STATUS:
            # A retry of the same kitchen handoff is a read, not a new sale.
            item_id = ticket[1]
            requested_quantity = ticket[2]
            ok = True
            remaining_stock = get_stock_status(item_id)
        else:
            requested_quantity = _validate_quantity(line["quantity"])
            availability = check_availability(line["item_id"], requested_quantity)
            ok = availability["available"]
            remaining_stock = availability["remaining_stock"]
            if ok:
                remaining_stock = remaining_stock - requested_quantity
                _STOCK[line["item_id"]] = remaining_stock
                _LINE_STATUS[line_id] = KitchenStatus.ORDER_RECEIVED
                _LINE_TICKETS[line_id] = (
                    payload["order_id"], line["item_id"], requested_quantity
                )
                _CANCELLED_LINES.discard((payload["order_id"], line_id))
        if not ok:
            all_available = False
        line_results.append({
            "line_id": line_id,
            "item_id": line["item_id"],
            "name": line["name"],
            "requested_quantity": requested_quantity,
            "available": ok,
            "remaining_stock": remaining_stock if ok else get_stock_status(line["item_id"]),
            "status": serialize_kitchen_status(_LINE_STATUS.get(line_id)),
        })
    return {
        "order_id": payload["order_id"],
        "accepted": all_available,
        "line_results": line_results,
    }


def get_line_status(order_id: str, line_id: str):
    # The kitchen integration contract continues to expose wire strings.
    ticket = _LINE_TICKETS.get(line_id)
    if ticket is not None and ticket[0] != order_id:
        return None
    return serialize_kitchen_status(_LINE_STATUS.get(line_id))


def cancel_line(order_id: str, line_id: str) -> dict:
    """
    Cancellable only while still 'received'. Once the kitchen has started
    cooking, the food exists and the cancellation is refused.
    """
    key = (order_id, line_id)
    ticket = _LINE_TICKETS.get(line_id)
    if key in _CANCELLED_LINES:
        return {
            "cancelled": True,
            "status": "received",
            "reason": "already cancelled",
        }
    if ticket is None or ticket[0] != order_id:
        # Never reached the kitchen, so there is nothing to cancel there.
        return {"cancelled": True, "status": None, "reason": "not sent to kitchen"}
    status = _LINE_STATUS.get(line_id)
    if status is None:
        return {"cancelled": True, "status": None, "reason": "already cancelled"}
    if status is KitchenStatus.ORDER_RECEIVED:
        _LINE_STATUS.pop(line_id, None)
        _STOCK[ticket[1]] = get_stock_status(ticket[1]) + ticket[2]
        _CANCELLED_LINES.add(key)
        return {
            "cancelled": True,
            "status": serialize_kitchen_status(status),
            "reason": "cancelled before preparation",
        }
    return {
        "cancelled": False,
        "status": serialize_kitchen_status(status),
        "reason": (
            "already being prepared"
            if status is KitchenStatus.IN_PREPARATION
            else "already prepared"
        ),
    }


# ---------------------------------------------------------------------- #
# Test/demo helpers — stand in for kitchen staff tapping the ticket board.
# ---------------------------------------------------------------------- #
def advance_line_status(line_id: str) -> str | None:
    """Move a line one step along received -> preparing -> done."""
    current = _LINE_STATUS.get(line_id)
    if current is None:
        return None
    if current is not KitchenStatus.DONE:
        _LINE_STATUS[line_id] = next_kitchen_status(current)
    return serialize_kitchen_status(_LINE_STATUS[line_id])


def reset_kitchen(stock: dict | None = None) -> None:
    """Reset stock and the ticket board, so demo scripts start from a clean slate."""
    global _STOCK
    _LINE_STATUS.clear()
    _LINE_TICKETS.clear()
    _CANCELLED_LINES.clear()
    if stock is not None:
        if any(
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 0
            for quantity in stock.values()
        ):
            raise ValueError("stock quantities must be non-negative integers")
        _STOCK = dict(stock)
    else:
        _STOCK = dict(_DEFAULT_STOCK)


def set_stock(item_id: str, quantity: int) -> None:
    """Force a stock level, for testing the out-of-stock path."""
    _validate_quantity(quantity)
    _STOCK[item_id] = quantity
