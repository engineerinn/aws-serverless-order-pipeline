# export_to_s3_for_athena
#
# Not part of the state machine. EventBridge invokes this once a day at
# 00:00 UTC (see analytics.tf); the Glue crawler picks the output up an hour
# later and Athena queries it.
#
# Output layout, which is what makes the partition work:
#   s3://<analytics-bucket>/analytics/export_date=YYYY-MM-DD/orders.json
#
# The file is newline-delimited JSON — one object per line, no wrapping array.
# That is the format Athena's JSON SerDe expects; a pretty-printed array will
# silently parse as a single malformed row.

import json
import logging
import os

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

TABLE_NAME = os.environ.get("ORDERS_TABLE", "orders")
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
EXPORT_PREFIX = os.environ.get("EXPORT_PREFIX", "analytics")


def normalise(value: Any) -> Any:
    """Make DynamoDB values JSON-serialisable.

    Decimal is the only surprise: boto3 returns every number as one, and
    json.dumps refuses it. Integral values become int so Athena infers
    bigint for quantity rather than double.
    """

    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, set):
        return sorted(normalise(v) for v in value)
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in value.items()}
    return value


def scan_table(table) -> Iterator[dict]:
    """Yield every item in the table, following pagination."""

    kwargs: dict = {}

    while True:
        response = table.scan(**kwargs)

        for item in response.get("Items", []):
            yield normalise(item)

        last_key = response.get("LastEvaluatedKey")

        if not last_key:
            return

        kwargs["ExclusiveStartKey"] = last_key


def to_ndjson(items: list) -> str:
    return "\n".join(json.dumps(item, separators=(",", ":")) for item in items)


def build_export_key(now: datetime | None = None, prefix: str = EXPORT_PREFIX) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{prefix}/export_date={now.strftime('%Y-%m-%d')}/orders.json"


def lambda_handler(event: dict, context: Any) -> dict:
    if not ANALYTICS_BUCKET:
        raise RuntimeError("ANALYTICS_BUCKET environment variable is not set")

    table = dynamodb.Table(TABLE_NAME)
    items = list(scan_table(table))
    key = build_export_key()

    if not items:
        logger.info(json.dumps({"event": "export_skipped", "reason": "table_empty"}))
        return {"exported_count": 0, "bucket": ANALYTICS_BUCKET, "key": None}

    s3.put_object(
        Bucket=ANALYTICS_BUCKET,
        Key=key,
        Body=to_ndjson(items).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(json.dumps({
        "event": "export_complete",
        "bucket": ANALYTICS_BUCKET,
        "key": key,
        "exported": len(items),
    }))

    return {"exported_count": len(items), "bucket": ANALYTICS_BUCKET, "key": key}
