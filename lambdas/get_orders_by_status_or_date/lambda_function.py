# get_orders_by_status_or_date
#
# Sits behind API Gateway, outside the state machine.
#
#   GET /orders?status=shipped&start_date=2024-01-01&end_date=2024-01-31
#   GET /orders?customer_id=CUST-123&limit=50
#
# Queries one of the two GSIs on the orders table rather than scanning:
#   status-date-index    hash=status       range=order_date
#   customer-date-index  hash=customer_id  range=order_date

import json
import logging
import os

from datetime import datetime
from decimal import Decimal
from typing import Any

import boto3

from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("ORDERS_TABLE", "orders")

STATUS_INDEX = "status-date-index"
CUSTOMER_INDEX = "customer-date-index"

VALID_STATUSES = {"pending", "processing", "shipped", "delivered", "cancelled"}

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class QueryError(ValueError):
    """Raised for anything the caller can fix by changing the query string."""


class _DecimalEncoder(json.JSONEncoder):
    """DynamoDB hands back every number as Decimal; json.dumps refuses it."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _parse_date(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise QueryError(f"'{field}' must be a date in YYYY-MM-DD format")
    return value


def _parse_limit(value: str | None) -> int:
    if value is None:
        return DEFAULT_LIMIT

    try:
        limit = int(value)
    except ValueError:
        raise QueryError("'limit' must be an integer")

    if limit < 1 or limit > MAX_LIMIT:
        raise QueryError(f"'limit' must be between 1 and {MAX_LIMIT}")

    return limit


def build_query(params: dict) -> dict:
    """Turn a query string into kwargs for table.query().

    Exactly one of status / customer_id picks the index. The date range is
    optional and applies to the sort key either way.
    """

    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}

    status = params.get("status")
    customer_id = params.get("customer_id")

    if status and customer_id:
        raise QueryError("Provide either 'status' or 'customer_id', not both")

    if status:
        if status not in VALID_STATUSES:
            raise QueryError(
                f"'status' must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        index_name = STATUS_INDEX
        condition = Key("status").eq(status)
    elif customer_id:
        index_name = CUSTOMER_INDEX
        condition = Key("customer_id").eq(customer_id)
    else:
        raise QueryError("Missing required parameter: 'status' or 'customer_id'")

    start_date = params.get("start_date")
    end_date = params.get("end_date")

    if start_date and end_date:
        start = _parse_date(start_date, "start_date")
        end = _parse_date(end_date, "end_date")

        if start > end:
            raise QueryError("'start_date' must not be after 'end_date'")

        condition = condition & Key("order_date").between(start, end)
    elif start_date:
        condition = condition & Key("order_date").gte(
            _parse_date(start_date, "start_date")
        )
    elif end_date:
        condition = condition & Key("order_date").lte(
            _parse_date(end_date, "end_date")
        )

    return {
        "IndexName": index_name,
        "KeyConditionExpression": condition,
        "Limit": _parse_limit(params.get("limit")),
        # Newest orders first — the common case for a dashboard.
        "ScanIndexForward": False,
    }


def _response(status_code: int, payload: Any) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload, cls=_DecimalEncoder),
    }


def lambda_handler(event: dict, context: Any) -> dict:
    params = event.get("queryStringParameters") or {}

    try:
        query_kwargs = build_query(params)
    except QueryError as exc:
        return _response(400, {"error": str(exc)})

    table = dynamodb.Table(TABLE_NAME)
    result = table.query(**query_kwargs)
    items = result.get("Items", [])

    logger.info(json.dumps({
        "event": "query_complete",
        "index": query_kwargs["IndexName"],
        "returned": len(items),
    }))

    return _response(200, {
        "count": len(items),
        "index": query_kwargs["IndexName"],
        "orders": items,
        # Present when more rows matched than fit in Limit — feed it back as
        # the caller's paging cursor if you extend this endpoint.
        "has_more": "LastEvaluatedKey" in result,
    })
