import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('FilteredCars')

def lambda_handler(event, context):
    filtered_rows = event['filter_results']['filtered_rows']
    
    for row in filtered_rows:
        print(f"Inserting into DynamoDB: {row['Brand']} - {row['Model']}")
        table.put_item(Item=row)

    return {
        "message": f"{len(filtered_rows)} items inserted into DynamoDB.",
        "inserted_count": len(filtered_rows),
        "filter_results": event['filter_results']
    }
