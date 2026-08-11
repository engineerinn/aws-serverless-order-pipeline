from decimal import Decimal

import pytest


@pytest.fixture(scope="module")
def save(lambda_module):
    return lambda_module("save_to_dynamodb")


def test_numeric_fields_become_decimal(save):
    item = save.to_dynamodb_item({
        "order_id": "ORD-001",
        "quantity": "2",
        "unit_price": "79.99",
        "total_value": 159.98,
    })

    assert isinstance(item["quantity"], Decimal)
    assert isinstance(item["unit_price"], Decimal)
    assert isinstance(item["total_value"], Decimal)


def test_price_keeps_exact_cents(save):
    """Decimal(79.99) is 79.9899999...; Decimal("79.99") is exact."""

    item = save.to_dynamodb_item({"order_id": "ORD-001", "unit_price": 79.99})

    assert item["unit_price"] == Decimal("79.99")


def test_strings_are_left_alone(save):
    item = save.to_dynamodb_item({
        "order_id": "ORD-001",
        "customer_id": "CUST-123",
        "status": "pending",
    })

    assert item["order_id"] == "ORD-001"
    assert item["status"] == "pending"


def test_empty_values_are_dropped(save):
    """DynamoDB rejects empty attribute names and stores None badly."""

    item = save.to_dynamodb_item({
        "order_id": "ORD-001",
        "product_name": "",
        "notes": None,
    })

    assert "product_name" not in item
    assert "notes" not in item
    assert item["order_id"] == "ORD-001"


def test_original_order_is_not_mutated(save):
    order = {"order_id": "ORD-001", "quantity": "2"}
    save.to_dynamodb_item(order)

    assert order["quantity"] == "2"


def test_handler_short_circuits_on_empty_batch(save):
    """No valid rows must not mean a call to DynamoDB."""

    event = {"summary": {"total": 3, "valid": 0, "invalid": 3}, "valid_orders": []}
    result = save.lambda_handler(event, None)

    assert result["saved_count"] == 0
    assert result["summary"] == event["summary"]
