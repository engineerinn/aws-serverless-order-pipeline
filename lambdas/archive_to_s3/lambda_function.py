# archive_to_s3
#
# Step 4 of the state machine. Moves the source CSV out of the landing bucket
# and writes the processed/rejected rows next to it as JSON.
#
# Input  : {bucket, source_key, valid_orders[], invalid_orders[], summary{}, ...}
# Output : a trimmed event — the row arrays are dropped so the payload handed
#          to NotifySuccess stays well under the 256 KB Step Functions limit.

import json
import logging
import os

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

ARCHIVE_BUCKET = os.environ.get("ARCHIVE_BUCKET", "")

# Leaving the CSV in the landing bucket is usually the wrong default: it makes
# re-runs ambiguous and the bucket grows forever. Override to "false" to keep it.
DELETE_SOURCE = os.environ.get("DELETE_SOURCE_OBJECT", "true").lower() == "true"


class _DecimalEncoder(json.JSONEncoder):
    """Rows may carry Decimals if a caller round-trips them through DynamoDB."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def build_archive_keys(source_key: str, now: datetime | None = None) -> dict:
    """Date-partitioned destination keys for one pipeline run.

    Partitioning by date keeps prefixes small and makes lifecycle rules and
    manual spelunking straightforward.
    """

    now = now or datetime.now(timezone.utc)
    stem = os.path.basename(source_key) or "orders.csv"
    partition = now.strftime("%Y/%m/%d")
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    return {
        "raw": f"raw/{partition}/{stamp}-{stem}",
        "processed": f"processed/{partition}/{stamp}-{stem}.json",
        "rejected": f"rejected/{partition}/{stamp}-{stem}.json",
    }


def _put_json(bucket: str, key: str, payload: Any) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, cls=_DecimalEncoder).encode("utf-8"),
        ContentType="application/json",
    )


def lambda_handler(event: dict, context: Any) -> dict:
    if not ARCHIVE_BUCKET:
        raise RuntimeError("ARCHIVE_BUCKET environment variable is not set")

    source_bucket = event["bucket"]
    source_key = event["source_key"]

    valid_orders = event.get("valid_orders", [])
    invalid_orders = event.get("invalid_orders", [])

    keys = build_archive_keys(source_key)

    # 1. Copy the original CSV so the raw input is always reproducible.
    s3.copy_object(
        Bucket=ARCHIVE_BUCKET,
        Key=keys["raw"],
        CopySource={"Bucket": source_bucket, "Key": source_key},
    )

    # 2. Store what the pipeline actually accepted.
    _put_json(ARCHIVE_BUCKET, keys["processed"], valid_orders)

    # 3. Only write a rejects file when there is something to look at.
    archived_keys = {"raw": keys["raw"], "processed": keys["processed"]}

    if invalid_orders:
        _put_json(ARCHIVE_BUCKET, keys["rejected"], invalid_orders)
        archived_keys["rejected"] = keys["rejected"]

    # 4. Clear the landing bucket last — only after the copy succeeded.
    if DELETE_SOURCE:
        s3.delete_object(Bucket=source_bucket, Key=source_key)

    logger.info(json.dumps({
        "event": "archive_complete",
        "archive_bucket": ARCHIVE_BUCKET,
        "keys": archived_keys,
        "source_deleted": DELETE_SOURCE,
    }))

    return {
        "bucket": source_bucket,
        "source_key": source_key,
        "summary": event.get("summary", {}),
        "saved_count": event.get("saved_count", 0),
        "archive_bucket": ARCHIVE_BUCKET,
        "archive_keys": archived_keys,
    }
