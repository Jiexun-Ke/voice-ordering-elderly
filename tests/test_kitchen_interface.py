import pytest

from backend.app import kitchen_interface as kitchen
from backend.app.models import KitchenStatus, Order, OrderLine


@pytest.fixture(autouse=True)
def clean_kitchen():
    kitchen.reset_kitchen()


def make_order(*lines):
    return Order(order_id="order-1", lines=list(lines))


def make_line(line_id, item_id="kopi", quantity=1):
    return OrderLine(
        line_id=line_id,
        item_id=item_id,
        item_name=item_id.replace("_", " ").title(),
        quantity=quantity,
        unit_price=1.2,
    )


def test_stock_reads_return_current_values_without_exposing_mutable_state():
    kitchen.reset_kitchen({"kopi": 4, "teh": 2})

    assert kitchen.get_stock_status("kopi") == 4
    assert kitchen.get_stock_status("unknown") == 0
    all_stock = kitchen.get_all_stock()
    all_stock["kopi"] = 99
    assert kitchen.get_stock_status("kopi") == 4


def test_check_availability_reports_requested_and_remaining_quantities():
    kitchen.reset_kitchen({"kopi": 4})

    assert kitchen.check_availability("kopi", 3) == {
        "item_id": "kopi",
        "requested_quantity": 3,
        "available": True,
        "remaining_stock": 4,
    }
    assert kitchen.check_availability("kopi", 5)["available"] is False
    assert kitchen.check_availability("kopi", 5)["remaining_stock"] == 4
    assert kitchen.check_availability("unknown", 1) == {
        "item_id": "unknown",
        "requested_quantity": 1,
        "available": False,
        "remaining_stock": 0,
    }


def test_availability_rejects_invalid_quantities():
    with pytest.raises(ValueError, match="non-negative integer"):
        kitchen.check_availability("kopi", -1)
    with pytest.raises(ValueError, match="non-negative integer"):
        kitchen.set_stock("kopi", -1)


def test_send_decrements_only_accepted_lines_and_preserves_partial_acceptance():
    kitchen.reset_kitchen({"kopi": 2, "teh": 1})
    accepted_line = make_line("line-accepted", "kopi", 2)
    rejected_line = make_line("line-rejected", "teh", 2)

    response = kitchen.send_order_to_kitchen(
        make_order(accepted_line, rejected_line),
        lines=[accepted_line, rejected_line],
    )

    assert response["accepted"] is False
    assert [result["line_id"] for result in response["line_results"]] == [
        "line-accepted",
        "line-rejected",
    ]
    assert response["line_results"][0]["available"] is True
    assert response["line_results"][0]["remaining_stock"] == 0
    assert response["line_results"][0]["status"] == "received"
    assert response["line_results"][1]["available"] is False
    assert response["line_results"][1]["remaining_stock"] == 1
    assert kitchen.get_stock_status("kopi") == 0
    assert kitchen.get_stock_status("teh") == 1


def test_exact_stock_is_accepted_and_stock_never_becomes_negative():
    kitchen.reset_kitchen({"kopi": 2})
    line = make_line("line-exact", quantity=2)

    result = kitchen.send_order_to_kitchen(make_order(line))["line_results"][0]

    assert result["available"] is True
    assert result["requested_quantity"] == 2
    assert kitchen.get_stock_status("kopi") == 0
    assert all(quantity >= 0 for quantity in kitchen.get_all_stock().values())


def test_accepted_line_starts_received_and_advances_forward():
    line = make_line("line-status")
    response = kitchen.send_order_to_kitchen(make_order(line))

    assert response["line_results"][0]["status"] == "received"
    assert kitchen.get_line_status("order-1", line.line_id) == "received"
    assert kitchen.advance_line_status(line.line_id) == "preparing"
    assert kitchen.get_line_status("order-1", line.line_id) == "preparing"
    assert kitchen.advance_line_status(line.line_id) == "done"
    assert kitchen.get_line_status("order-1", line.line_id) == "done"


def test_received_cancellation_restores_exact_stock_once_and_is_idempotent():
    kitchen.reset_kitchen({"kopi": 5})
    line = make_line("line-cancel", quantity=2)
    kitchen.send_order_to_kitchen(make_order(line))
    assert kitchen.get_stock_status("kopi") == 3

    first = kitchen.cancel_line("order-1", line.line_id)
    second = kitchen.cancel_line("order-1", line.line_id)

    assert first == {
        "cancelled": True,
        "status": "received",
        "reason": "cancelled before preparation",
    }
    assert second["cancelled"] is True
    assert second["reason"] == "already cancelled"
    assert kitchen.get_stock_status("kopi") == 5
    assert kitchen.get_line_status("order-1", line.line_id) is None


@pytest.mark.parametrize(
    "advances, expected_status, expected_reason",
    [
        (1, KitchenStatus.IN_PREPARATION.value, "already being prepared"),
        (2, KitchenStatus.DONE.value, "already prepared"),
    ],
)
def test_cancellation_is_rejected_after_preparation_starts(
    advances, expected_status, expected_reason
):
    kitchen.reset_kitchen({"kopi": 5})
    line = make_line("line-too-late", quantity=2)
    kitchen.send_order_to_kitchen(make_order(line))
    for _ in range(advances):
        kitchen.advance_line_status(line.line_id)

    result = kitchen.cancel_line("order-1", line.line_id)

    assert result["cancelled"] is False
    assert result["status"] == expected_status
    assert result["reason"] == expected_reason
    assert kitchen.get_stock_status("kopi") == 3


def test_repeated_send_of_an_active_line_does_not_deduct_stock_twice():
    kitchen.reset_kitchen({"kopi": 3})
    line = make_line("line-retry", quantity=2)
    order = make_order(line)

    first = kitchen.send_order_to_kitchen(order)
    second = kitchen.send_order_to_kitchen(order)

    assert first["line_results"][0]["status"] == "received"
    assert second["line_results"][0]["status"] == "received"
    assert kitchen.get_stock_status("kopi") == 1
