from datetime import datetime, timezone

import pytest


@pytest.fixture(scope="module")
def archive(lambda_module):
    return lambda_module("archive_to_s3")


FIXED_NOW = datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)


def test_keys_are_date_partitioned(archive):
    keys = archive.build_archive_keys("orders.csv", now=FIXED_NOW)

    assert keys["raw"] == "raw/2024/01/15/20240115T093000Z-orders.csv"
    assert keys["processed"] == "processed/2024/01/15/20240115T093000Z-orders.csv.json"
    assert keys["rejected"] == "rejected/2024/01/15/20240115T093000Z-orders.csv.json"


def test_nested_source_key_keeps_only_the_filename(archive):
    keys = archive.build_archive_keys("incoming/2024/orders.csv", now=FIXED_NOW)

    assert keys["raw"].endswith("-orders.csv")
    assert "incoming" not in keys["raw"]


def test_directory_style_key_falls_back_to_a_default(archive):
    keys = archive.build_archive_keys("incoming/", now=FIXED_NOW)

    assert keys["raw"].endswith("-orders.csv")


def test_prefixes_are_distinct(archive):
    keys = archive.build_archive_keys("orders.csv", now=FIXED_NOW)

    assert len({k.split("/")[0] for k in keys.values()}) == 3
