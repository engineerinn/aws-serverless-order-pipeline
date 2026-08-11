# notify_via_sns
#
# Terminal step of the state machine, invoked from two places:
#
#   NotifySuccess -> {"status": "SUCCESS", "summary": {total, valid, invalid}}
#   NotifyFailure -> {"status": "FAILURE", "error": {"Error": ..., "Cause": ...}}
#
# See the Parameters blocks in step_function/order_workflow.asl.json.

import json
import logging
import os

from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")

TOPIC_ARN = os.environ.get("SNS_TOPIC", "")
PROJECT = os.environ.get("PROJECT_NAME", "order-pipeline")

# SNS caps Subject at 100 ASCII characters and rejects newlines, so the prefix
# is kept short and the detail all lives in the body.
SUBJECT_MAX = 100


def build_notification(event: dict) -> tuple[str, str]:
    """Return the (subject, message) pair for one pipeline outcome."""

    status = str(event.get("status", "SUCCESS")).upper()

    if status == "FAILURE":
        error = event.get("error") or {}

        if isinstance(error, str):
            error = {"Error": error, "Cause": ""}

        subject = f"[{PROJECT}] Order pipeline FAILED"
        message = (
            "The order pipeline did not complete.\n\n"
            f"Error: {error.get('Error', 'Unknown')}\n"
            f"Cause: {error.get('Cause', 'No cause reported')}\n\n"
            "Check the Step Functions execution history and CloudWatch logs."
        )

        return subject[:SUBJECT_MAX], message

    summary = event.get("summary") or {}
    total = summary.get("total", 0)
    valid = summary.get("valid", 0)
    invalid = summary.get("invalid", 0)

    if invalid:
        subject = f"[{PROJECT}] Orders processed with {invalid} rejected"
    else:
        subject = f"[{PROJECT}] Orders processed successfully"

    message = (
        "The order pipeline finished.\n\n"
        f"Rows read:     {total}\n"
        f"Rows accepted: {valid}\n"
        f"Rows rejected: {invalid}\n"
    )

    if invalid:
        message += "\nRejected rows were archived under the rejected/ prefix."

    return subject[:SUBJECT_MAX], message


def lambda_handler(event: dict, context: Any) -> dict:
    if not TOPIC_ARN:
        raise RuntimeError("SNS_TOPIC environment variable is not set")

    subject, message = build_notification(event)

    response = sns.publish(TopicArn=TOPIC_ARN, Subject=subject, Message=message)

    logger.info(json.dumps({
        "event": "notification_sent",
        "status": event.get("status", "SUCCESS"),
        "message_id": response.get("MessageId"),
    }))

    return {"status": "notification_sent", "subject": subject}
