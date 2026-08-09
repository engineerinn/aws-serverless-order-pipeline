import pytest

from lambda_function import validate_row

def test_valid_order():

    row = {
        "order_id": "ORD-001", "customer_id": "CUST-123",
        "product_name": "Widget", "quantity": "2",
        "unit_price": "9.99", "order_date": "2024-01-15", "status": "pending"
    }

    is_valid, reason = validate_row(row)
    assert is_valid
    assert reason == "ok"

def test_invalid_order_id_format():

    row = {
        "order_id": "INVALID", "customer_id": "CUST-123",
        "product_name": "Widget", "quantity": "2",
        "unit_price": "9.99", "order_date": "2024-01-15", "status": "pending"

    }

    is_valid, reason = validate_row(row)
    assert not is_valid
    assert reason == "invalid_order_id_format"

def test_negative_quantity():

    row = {

        "order_id": "ORD-002", "customer_id": "CUST-456",
        "product_name": "Widget", "quantity": "-1",
        "unit_price": "9.99", "order_date": "2024-01-15", "status": "pending"
    }
    is_valid, reason = validate_row(row)
    assert not is_valid
    assert reason == "invalid_quantity"
