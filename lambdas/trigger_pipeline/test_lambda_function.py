import pytest


@pytest.fixture(scope="module")
def trigger(lambda_module):
    return lambda_module("trigger_pipeline")


def _record(bucket, key):
    return {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}


def test_extracts_bucket_and_key(trigger):
    location = trigger.extract_s3_location(_record("raw-orders", "orders.csv"))

    assert location == {"bucket": "raw-orders", "key": "orders.csv"}


def test_decodes_spaces_in_key(trigger):
    """S3 sends "jan orders.csv" as "jan+orders.csv"."""

    location = trigger.extract_s3_location(_record("raw-orders", "jan+orders.csv"))

    assert location["key"] == "jan orders.csv"


def test_decodes_percent_escapes_in_key(trigger):
    location = trigger.extract_s3_location(
        _record("raw-orders", "incoming/2024%3A01/orders%231.csv")
    )

    assert location["key"] == "incoming/2024:01/orders#1.csv"
