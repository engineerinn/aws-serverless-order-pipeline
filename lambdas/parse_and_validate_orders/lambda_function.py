import boto3
import csv
import io
import json

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = event['bucket']
    key = event['key']

    response = s3.get_object(Bucket=bucket, Key=key)
    raw_data = response['Body'].read()

    try:
        data = raw_data.decode('utf-8')
    except UnicodeDecodeError:
        data = raw_data.decode('latin-1')

    csv_reader = csv.DictReader(io.StringIO(data))
    rows = [row for row in csv_reader]

    return {
        "rows": rows,
        "bucket": bucket,
        "key": key
    }
