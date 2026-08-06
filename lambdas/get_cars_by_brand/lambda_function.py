import json
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('FilteredCars')

def lambda_handler(event, context):
    params = event.get('queryStringParameters', {})
    brand = params.get('brand')

    if not brand:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'brand' parameter"})
        }

    response = table.query(
        KeyConditionExpression=Key('Brand').eq(brand)
    )

    return {
        "statusCode": 200,
        "body": json.dumps(response.get('Items', []))
    }
