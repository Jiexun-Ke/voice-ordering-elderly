"""
Per-table session storage.

A table keeps ONE running tab from the moment the customer sits down until
they pay. Ordering more food appends to that tab rather than starting over,
and the total accumulates. Payment is the only thing that clears a table —
without that, one customer's bill would follow the next person who sits down.

State is held in memory and mirrored to a JSON file, so a restart mid-service
doesn't lose everyone's tab.

WHAT IS NOT PERSISTED: an open `pending` clarification. It holds live
ModifierGroup references, and a half-built item isn't on the bill yet anyway.
After a restart the customer is simply asked again — safe, if slightly
repetitive.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    Order,
    OrderLine,
    Session,
    normalize_kitchen_status,
    serialize_kitchen_status,
)


def _new_session(table_id: str) -> Session:
    return Session(
        session_id=str(uuid.uuid4()),
        order=Order(order_id=str(uuid.uuid4())),
        table_id=table_id,
    )


class SessionStore:
    """Tables in memory, mirrored to JSON. `path=None` disables persistence."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else None
        self._sessions: dict[str, Session] = {}
        self.receipts: list[dict] = []
        if self.path and self.path.exists():
            self._load()

    # ------------------------------------------------------------------ #
    # Tables
    # ------------------------------------------------------------------ #
    def get(self, table_id: str) -> Session:
        """The table's open tab, creating a fresh one if nobody is seated."""
        table_id = str(table_id)
        if table_id not in self._sessions:
            self._sessions[table_id] = _new_session(table_id)
        return self._sessions[table_id]

    def tables(self) -> list[str]:
        return sorted(self._sessions.keys())

    def bill_for(self, table_id: str) -> dict:
        session = self.get(table_id)
        return self._bill(session)

    # ------------------------------------------------------------------ #
    # Payment — the only thing that clears a table
    # ------------------------------------------------------------------ #
    def mark_paid(self, table_id: str) -> Optional[dict]:
        """
        Settle the tab: stamp it paid, archive a receipt, and seat the table
        fresh so the next customer starts at zero.

        Returns the receipt, or None if there was nothing to pay for.
        """
        session = self.get(str(table_id))
        if not session.order.lines:
            return None

        session.order.status = "paid"
        session.order.paid_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        receipt = self._bill(session)
        receipt["paid_at"] = session.order.paid_at
        self.receipts.append(receipt)

        # Fresh session, so nothing carries over to the next customer.
        self._sessions[str(table_id)] = _new_session(str(table_id))
        self.save()
        return receipt

    def _bill(self, session: Session) -> dict:
        return {
            "table_id": session.table_id,
            "order_id": session.order.order_id,
            "takeaway": session.order.takeaway,
            "lines": [
                {
                    "item": l.item_name,
                    "quantity": l.quantity,
                    "modifiers": l.modifier_names,
                    "unit_price": l.unit_price,
                    "subtotal": l.subtotal,
                    "kitchen_status": serialize_kitchen_status(l.kitchen_status),
                }
                for l in session.order.lines
            ],
            "total": session.order.total,
        }

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tables": {tid: self._session_to_dict(s) for tid, s in self._sessions.items()},
            "receipts": self.receipts,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt or unreadable file must not stop service — start clean.
            return
        self.receipts = data.get("receipts", [])
        for table_id, raw in data.get("tables", {}).items():
            self._sessions[table_id] = self._session_from_dict(table_id, raw)

    @staticmethod
    def _session_to_dict(session: Session) -> dict:
        return {
            "session_id": session.session_id,
            "history": session.history,
            "order": {
                "order_id": session.order.order_id,
                "status": session.order.status,
                "takeaway": session.order.takeaway,
                "paid_at": session.order.paid_at,
                "lines": [
                    {
                        "line_id": l.line_id,
                        "item_id": l.item_id,
                        "item_name": l.item_name,
                        "quantity": l.quantity,
                        "unit_price": l.unit_price,
                        "modifiers": l.modifiers,
                        "modifier_names": l.modifier_names,
                        "sent": l.sent,
                        "kitchen_status": serialize_kitchen_status(l.kitchen_status),
                    }
                    for l in session.order.lines
                ],
            },
        }

    @staticmethod
    def _session_from_dict(table_id: str, raw: dict) -> Session:
        raw_order = raw.get("order", {})
        order = Order(
            order_id=raw_order.get("order_id", str(uuid.uuid4())),
            status=raw_order.get("status", "in_progress"),
            takeaway=raw_order.get("takeaway"),
            paid_at=raw_order.get("paid_at"),
            lines=[
                OrderLine(
                    line_id=l["line_id"],
                    item_id=l["item_id"],
                    item_name=l["item_name"],
                    quantity=l["quantity"],
                    unit_price=l["unit_price"],
                    modifiers=l.get("modifiers", {}),
                    modifier_names=l.get("modifier_names", {}),
                    sent=l.get("sent", False),
                    kitchen_status=normalize_kitchen_status(l.get("kitchen_status")),
                )
                for l in raw_order.get("lines", [])
            ],
        )
        return Session(
            session_id=raw.get("session_id", str(uuid.uuid4())),
            order=order,
            table_id=table_id,
            history=raw.get("history", []),
        )
