import json
import boto3
from datetime import datetime

VALID_BRANDS = {
    "Kia", "Mercedes", "Alfa Romeo"
}

s3 = boto3.client('s3')
REPORT_BUCKET = '<insert_report_output_s3_bucket_name_here>' # Create your own table. This will store reports about the data query
def lambda_handler(event, context):
    rows = event['rows']
    filtered_rows = []
    rejected_rows = []

    for row in rows:
        brand = row['Brand'].strip().title()
        model = row['Model'].strip().title()

        if brand in VALID_BRANDS:
            row['Brand'] = brand
            row['Model'] = model
            row['timestamp'] = datetime.utcnow().isoformat()
            filtered_rows.append(row)
        else:
            rejected_rows.append(row)

    summary = {
        "accepted": len(filtered_rows),
        "rejected": len(rejected_rows),
        "timestamp": datetime.utcnow().isoformat()
    }

    # Upload report to S3 (Optional)
    s3.put_object(
        Bucket=REPORT_BUCKET,
        Key='processing_report.json',
        Body=json.dumps(summary),
        ContentType='application/json'
    )

    return {
    "filtered_rows": filtered_rows,
    "rejected_rows": rejected_rows,
    "summary": {
        "accepted": len(filtered_rows),
        "rejected": len(rejected_rows),
        "timestamp": datetime.utcnow().isoformat()
    }
}

