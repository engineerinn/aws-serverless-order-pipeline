# parse_and_validate_orders

from datetime import datetime
from typing import Any
import boto3
import csv
import io
import json
import re
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

REQUIRED_FIELDS = {"order_id", "customer_id", "product_name", "quantity", "unit_price", "order_date", "status"}
VALID_STATUSES = {"pending", "processing", "shipped", "delivered", "cancelled"}

def validate_row(row: dict) -> tuple[bool, str]:

    if not REQUIRED_FIELDS.issubset(row.keys()):
        return False, "missing_required_fields"
    if not re.match(r"^ORD-\d+$", row["order_id"]):
        return False, "invalid_order_id_format"

    try:
        qty = int(row["quantity"])
        if qty <= 0:
            return False, "invalid_quantity"
    except ValueError:
        return False, "quantity_not_integer"

    try:
        price = float(row["unit_price"])
        if price <= 0:
            return False, "invalid_price"
    except ValueError:
        return False, "price_not_float"

    try:
        datetime.strptime(row["order_date"], "%Y-%m-%d")
    except ValueError:
        return False, "invalid_date_format"

    if row["status"] not in VALID_STATUSES:
        return False, "invalid_status"

    return True, "ok"


def lambda_handler(event, context):
    bucket = event['bucket']
    key = event['key']

    response = s3.get_object(Bucket=bucket, Key=key)
    raw_data = response['Body'].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw_data))
    valid_orders = []
    invalid_orders = []

    for row in reader:
        is_valid, reason = validate_row(row)

        if is_valid:
            valid_orders.append(dict(row))
        else:
            invalid_orders.append({"row": dict(row), "reason": reason})

    logger.info(json.dumps({

        "event": "parsing_complete",
        "total": len(valid_orders) + len(invalid_orders),
        "valid": len(valid_orders),
        "invalid": len(invalid_orders),

    }))

    return {
        "bucket": bucket,
        "source_key": key,
        "valid_orders": valid_orders,
        "invalid_orders": invalid_orders,
        "summary": {"total": len(valid_orders) + len(invalid_orders), "valid": len(valid_orders),
                    "invalid": len(invalid_orders)},
    }

