import boto3
import os
import json

stepfunctions = boto3.client('stepfunctions')

def lambda_handler(event, context):
    # Parse S3 event
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']

    # Input format expected by your state machine
    input_payload = {
        "bucket": bucket,
        "key": key
    }

    response = stepfunctions.start_execution(
        stateMachineArn=os.environ['STEP_FUNCTION_ARN'],
        input=json.dumps(input_payload)
    )

    return {
        'statusCode': 200,
        'body': json.dumps("Step Function started successfully"),
        'executionArn': response['executionArn']
    }
