import pytest


@pytest.fixture(scope="module")
def parse(lambda_module):
    return lambda_module("parse_and_validate_orders")


def make_row(**overrides):
    row = {
        "order_id": "ORD-001",
        "customer_id": "CUST-123",
        "product_name": "Widget",
        "quantity": "2",
        "unit_price": "9.99",
        "order_date": "2024-01-15",
        "status": "pending",
    }
    row.update(overrides)
    return row


def test_valid_order(parse):
    is_valid, reason = parse.validate_row(make_row())

    assert is_valid
    assert reason == "ok"


def test_invalid_order_id_format(parse):
    is_valid, reason = parse.validate_row(make_row(order_id="INVALID"))

    assert not is_valid
    assert reason == "invalid_order_id_format"


def test_negative_quantity(parse):
    is_valid, reason = parse.validate_row(make_row(quantity="-1"))

    assert not is_valid
    assert reason == "invalid_quantity"


def test_missing_required_field(parse):
    row = make_row()
    del row["customer_id"]

    is_valid, reason = parse.validate_row(row)

    assert not is_valid
    assert reason == "missing_required_fields"


def test_non_integer_quantity(parse):
    is_valid, reason = parse.validate_row(make_row(quantity="two"))

    assert not is_valid
    assert reason == "quantity_not_integer"


def test_zero_price_is_rejected(parse):
    is_valid, reason = parse.validate_row(make_row(unit_price="0"))

    assert not is_valid
    assert reason == "invalid_price"


def test_non_numeric_price(parse):
    is_valid, reason = parse.validate_row(make_row(unit_price="free"))

    assert not is_valid
    assert reason == "price_not_float"


@pytest.mark.parametrize("bad_date", ["15-01-2024", "2024/01/15", "not-a-date", ""])
def test_invalid_date_formats(parse, bad_date):
    is_valid, reason = parse.validate_row(make_row(order_date=bad_date))

    assert not is_valid
    assert reason == "invalid_date_format"


def test_unknown_status(parse):
    is_valid, reason = parse.validate_row(make_row(status="refunded"))

    assert not is_valid
    assert reason == "invalid_status"


@pytest.mark.parametrize(
    "status", ["pending", "processing", "shipped", "delivered", "cancelled"]
)
def test_every_documented_status_is_accepted(parse, status):
    is_valid, _ = parse.validate_row(make_row(status=status))

    assert is_valid
