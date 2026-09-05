import json
from dataclasses import asdict

import pytest

from backend.app.models import (
    KitchenStatus,
    OrderLine,
    validate_kitchen_transition,
)
from backend.app.session_store import SessionStore


def make_line(status=None):
    return OrderLine(
        line_id="line-1",
        item_id="kopi",
        item_name="Kopi",
        quantity=1,
        unit_price=1.2,
        kitchen_status=status,
    )


def test_kitchen_status_uses_compatible_wire_values():
    assert KitchenStatus.ORDER_RECEIVED.value == "received"
    assert KitchenStatus.IN_PREPARATION.value == "preparing"
    assert KitchenStatus.DONE.value == "done"


def test_kitchen_status_allows_only_forward_transitions():
    assert validate_kitchen_transition(None, KitchenStatus.ORDER_RECEIVED) is KitchenStatus.ORDER_RECEIVED
    assert validate_kitchen_transition(
        KitchenStatus.ORDER_RECEIVED, KitchenStatus.IN_PREPARATION
    ) is KitchenStatus.IN_PREPARATION
    assert validate_kitchen_transition(
        KitchenStatus.IN_PREPARATION, KitchenStatus.DONE
    ) is KitchenStatus.DONE

    with pytest.raises(ValueError, match="Invalid kitchen status transition"):
        validate_kitchen_transition(KitchenStatus.IN_PREPARATION, KitchenStatus.ORDER_RECEIVED)
    with pytest.raises(ValueError, match="Invalid kitchen status transition"):
        validate_kitchen_transition(KitchenStatus.ORDER_RECEIVED, KitchenStatus.DONE)


def test_kitchen_status_is_json_safe_with_existing_wire_value():
    encoded = json.dumps(asdict(make_line(KitchenStatus.ORDER_RECEIVED)))
    assert '"kitchen_status": "received"' in encoded


def test_kitchen_status_persists_as_string_and_loads_as_enum(tmp_path):
    path = tmp_path / "sessions.json"
    store = SessionStore(str(path))
    session = store.get("table-1")
    session.order.lines.append(make_line("preparing"))
    store.save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    persisted = raw["tables"]["table-1"]["order"]["lines"][0]
    assert persisted["kitchen_status"] == "preparing"

    reloaded = SessionStore(str(path))
    restored = reloaded.get("table-1").order.lines[0]
    assert restored.kitchen_status is KitchenStatus.IN_PREPARATION
