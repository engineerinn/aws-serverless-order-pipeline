#enrich_orders

import json
import logging
import uuid

from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def enrich_order(order: dict) -> dict:

    """Add computed fields to each order."""

    order["total_value"] = round(float(order["unit_price"]) * int(order["quantity"]), 2)
    order["processed_at"] = datetime.now(timezone.utc).isoformat()
    order["pipeline_run_id"] = str(uuid.uuid4())

    return order

def lambda_handler(event: dict, context: Any) -> dict:

    valid_orders = event["valid_orders"]
    enriched = [enrich_order(o) for o in valid_orders]
    logger.info(json.dumps({"event": "enrichment_complete", "count": len(enriched)}))

    return {**event, "valid_orders": enriched}
