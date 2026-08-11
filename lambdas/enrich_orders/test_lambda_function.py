from datetime import datetime

import pytest


@pytest.fixture(scope="module")
def enrich(lambda_module):
    return lambda_module("enrich_orders")


def test_total_value_is_price_times_quantity(enrich):
    order = enrich.enrich_order({"quantity": "3", "unit_price": "9.99"})

    assert order["total_value"] == 29.97


def test_total_value_is_rounded_to_cents(enrich):
    """0.1 * 3 is 0.30000000000000004 in binary floating point."""

    order = enrich.enrich_order({"quantity": "3", "unit_price": "0.10"})

    assert order["total_value"] == 0.3


def test_processed_at_is_iso_utc(enrich):
    order = enrich.enrich_order({"quantity": "1", "unit_price": "1.00"})
    parsed = datetime.fromisoformat(order["processed_at"])

    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_run_id_is_unique_per_row(enrich):
    first = enrich.enrich_order({"quantity": "1", "unit_price": "1.00"})
    second = enrich.enrich_order({"quantity": "1", "unit_price": "1.00"})

    assert first["pipeline_run_id"] != second["pipeline_run_id"]


def test_handler_preserves_other_event_keys(enrich):
    event = {
        "bucket": "raw-orders",
        "source_key": "orders.csv",
        "valid_orders": [{"quantity": "2", "unit_price": "5.00"}],
        "invalid_orders": [],
        "summary": {"total": 1, "valid": 1, "invalid": 0},
    }

    result = enrich.lambda_handler(event, None)

    assert result["bucket"] == "raw-orders"
    assert result["source_key"] == "orders.csv"
    assert result["summary"] == {"total": 1, "valid": 1, "invalid": 0}
    assert result["valid_orders"][0]["total_value"] == 10.0


def test_handler_tolerates_an_empty_batch(enrich):
    result = enrich.lambda_handler({"valid_orders": []}, None)

    assert result["valid_orders"] == []
