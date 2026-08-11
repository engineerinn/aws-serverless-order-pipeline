# save_to_dynamodb
#
# Step 3 of the state machine. Takes the enriched rows produced by
# `enrich_orders` and persists them to the DynamoDB orders table.
#
# Input  : {bucket, source_key, valid_orders[], invalid_orders[], summary{}}
# Output : the same event plus {saved_count, table_name}

import json
import logging
import os

from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("ORDERS_TABLE", "orders")

# DynamoDB stores these as numbers so Athena and the query API can range over
# them; everything else stays a string.
NUMERIC_FIELDS = ("quantity", "unit_price", "total_value")


def to_dynamodb_item(order: dict) -> dict:
    """Convert one enriched order into a DynamoDB-safe item.

    DynamoDB rejects Python floats outright, so numbers go through Decimal.
    Note the str() — Decimal(79.99) is 79.989999... whereas Decimal("79.99")
    is exactly 79.99.
    """

    item = {k: v for k, v in order.items() if v is not None and v != ""}

    for field in NUMERIC_FIELDS:
        if field in item:
            item[field] = Decimal(str(item[field]))

    return item


def lambda_handler(event: dict, context: Any) -> dict:
    orders = event.get("valid_orders", [])

    if not orders:
        logger.info(json.dumps({"event": "save_skipped", "reason": "no_valid_orders"}))
        return {**event, "saved_count": 0, "table_name": TABLE_NAME}

    table = dynamodb.Table(TABLE_NAME)

    # batch_writer handles the 25-item batch limit and retries unprocessed
    # items. overwrite_by_pkeys drops in-batch duplicates so a CSV that lists
    # the same order_id twice doesn't blow up the whole batch.
    with table.batch_writer(overwrite_by_pkeys=["order_id"]) as batch:
        for order in orders:
            batch.put_item(Item=to_dynamodb_item(order))

    logger.info(json.dumps({
        "event": "save_complete",
        "table": TABLE_NAME,
        "saved": len(orders),
    }))

    return {**event, "saved_count": len(orders), "table_name": TABLE_NAME}
