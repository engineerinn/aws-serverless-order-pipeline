# trigger_pipeline
#
# Entry point. S3 invokes this on every .csv landing in the raw-orders bucket
# and it hands the location to the state machine.

import json
import logging
import os

from typing import Any
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

stepfunctions = boto3.client("stepfunctions")

STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN", "")


def extract_s3_location(record: dict) -> dict:
    """Pull bucket and key out of one S3 event record.

    S3 URL-encodes object keys in notifications: "jan orders.csv" arrives as
    "jan+orders.csv" and would 404 on GetObject if passed through as-is.
    """

    return {
        "bucket": record["s3"]["bucket"]["name"],
        "key": unquote_plus(record["s3"]["object"]["key"]),
    }


def lambda_handler(event: dict, context: Any) -> dict:
    if not STEP_FUNCTION_ARN:
        raise RuntimeError("STEP_FUNCTION_ARN environment variable is not set")

    # S3 can batch several objects into one invocation.
    executions = []

    for record in event.get("Records", []):
        payload = extract_s3_location(record)

        logger.info(json.dumps({"event": "pipeline_triggered", **payload}))

        response = stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps(payload),
        )

        executions.append(response["executionArn"])

    return {
        "statusCode": 200,
        "body": json.dumps(f"Started {len(executions)} execution(s)"),
        "executionArns": executions,
    }
