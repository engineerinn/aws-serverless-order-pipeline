import boto3
import json
import os

sns = boto3.client('sns')
TOPIC_ARN = os.environ['SNS_TOPIC'] # Replace this with your own topic arn here
def lambda_handler(event, context):
    summary = event.get('summary', {})
    accepted = summary.get('accepted', 0)
    rejected = summary.get('rejected', 0)
    timestamp = summary.get('timestamp', 'N/A')

    message = f"File processed at {timestamp}.\n\nAccepted: {accepted}\nRejected: {rejected}"

    if rejected > 0:
        subject = "🚨 Car Inventory Processing: Rejections Found"
    else:
        subject = "✅ Car Inventory Processed Successfully"

    response = sns.publish(
        TopicArn=TOPIC_ARN,
        Subject=subject,
        Message=message
    )

    print("SNS response:", response)
    return {"status": "Notification sent"}
