import json

from datetime import datetime, timezone
from decimal import Decimal

import pytest


@pytest.fixture(scope="module")
def export(lambda_module):
    return lambda_module("export_to_s3_for_athena")


def test_integral_decimals_become_ints(export):
    """Athena should infer bigint for quantity, not double."""

    assert export.normalise(Decimal("2")) == 2
    assert isinstance(export.normalise(Decimal("2")), int)


def test_fractional_decimals_become_floats(export):
    assert export.normalise(Decimal("79.99")) == 79.99


def test_nested_structures_are_walked(export):
    result = export.normalise({
        "order_id": "ORD-001",
        "unit_price": Decimal("9.99"),
        "tags": [Decimal("1"), {"qty": Decimal("3")}],
    })

    assert result == {"order_id": "ORD-001", "unit_price": 9.99, "tags": [1, {"qty": 3}]}


def test_sets_become_sorted_lists(export):
    assert export.normalise({"a", "c", "b"}) == ["a", "b", "c"]


def test_ndjson_is_one_object_per_line(export):
    body = export.to_ndjson([{"order_id": "ORD-001"}, {"order_id": "ORD-002"}])
    lines = body.split("\n")

    assert len(lines) == 2
    assert json.loads(lines[1])["order_id"] == "ORD-002"
    assert not body.startswith("[")


def test_export_key_is_hive_partitioned(export):
    now = datetime(2024, 3, 9, tzinfo=timezone.utc)

    assert export.build_export_key(now, prefix="analytics") == (
        "analytics/export_date=2024-03-09/orders.json"
    )


def test_scan_follows_pagination(export):
    class FakeTable:
        def __init__(self):
            self.calls = []

        def scan(self, **kwargs):
            self.calls.append(kwargs)

            if "ExclusiveStartKey" not in kwargs:
                return {
                    "Items": [{"order_id": "ORD-001"}],
                    "LastEvaluatedKey": {"order_id": "ORD-001"},
                }

            return {"Items": [{"order_id": "ORD-002"}]}

    table = FakeTable()
    items = list(export.scan_table(table))

    assert [i["order_id"] for i in items] == ["ORD-001", "ORD-002"]
    assert len(table.calls) == 2
