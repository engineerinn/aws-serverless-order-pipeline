# AWS Serverless Order Processing Pipeline
> Event-driven, serverless pipeline for processing and analysing e-commerce orders at scale.
Steps.

**Project Objective**
[Kasih Penjelasan]

**Deployment Steps**
[Kasih Penjelasan]

1. Create / login into AWS account.
2. Create / assign an IAM user for providing credentials to GitHub Actions and Terraform
3.  

![CI](https://github.com/YOUR_USERNAME/aws-order-pipeline/actions/workflows/deploy.yml/badge.svg)

![License](https://img.shields.io/badge/license-MIT-blue.svg)

Drop a CSV of orders into S3 and the pipeline validates it, enriches it, stores
it, archives it, and emails you the result — then exports everything to Athena
once a day so you can query it with SQL.

## Architecture

![Solution architecture](solution_architecture_diagram.png)

```
CSV upload to S3
      |
      v
trigger_pipeline  --start_execution-->  Step Functions
                                              |
        +-------------------------------------+-------------------------------------+
        |                |               |               |                |
        v                v               v               v                v
  ParseAndValidate  EnrichOrders   SaveToDynamoDB   ArchiveToS3     NotifySuccess
   (CSV -> rows)   (totals, ids)  (orders table)  (archive bucket)   (SNS email)

**AWS** [Pada setiap AWS produk, harus dikasih penjelasan singkat dan rolenya dalam proyek ini!]
1. S3
2. Lambda
3. Step Functions
4. DynamoDB
5. SQS (Simple Queue Service)
6. SNS (Simple Notification Service)
7. EventBridge
8. API Gateway
9. Glue
10. Athena
11. CloudWatch
12. X-Ray
13. Secrets Manager
  Any States.ALL error  ->  NotifyFailure  ->  PipelineFailed

**IaC**
Side paths
  EventBridge (daily 00:00 UTC)  ->  export_to_s3_for_athena  ->  S3 + Glue + Athena
  API Gateway  GET /orders       ->  get_orders_by_status_or_date  ->  DynamoDB GSIs
```

Terraform
[kasih penjelasan singkat mengenai Terraform dan perannya dalam proyek ini]

**CI/CD**
GitHub Actions
[kasih penjelasan singkat mengenai GitHub Actions dan perannya dalam proyek ini]

Language: Python 3.12

## Features

- Row-level CSV validation with a typed rejection reason for every bad row
- Orchestrated workflow with per-step retries, backoff, and a catch-all failure branch
- One IAM role per Lambda, each scoped to the resources it actually touches
- Dead letter queue for the two asynchronously invoked functions
- Date-partitioned archive with lifecycle tiering to Glacier
- Daily Athena export written as newline-delimited JSON, Hive-partitioned by date
- Query API over the DynamoDB GSIs — by status or by customer, with a date range
- CloudWatch dashboard plus alarms on execution failures and DLQ depth
- 70 unit tests, no AWS calls, run on every push

## Getting started

### Prerequisites

- Terraform >= 1.6, Python 3.12
- AWS credentials in the environment with permission to create the resources above

### Deploy

```bash
cd infra/terraform
terraform init
terraform apply -var="alert_email=you@example.com"
```

Terraform zips each `lambdas/*/` folder itself — there is no separate build step.

After the first apply, **confirm the SNS subscription email** or you will not
receive any notifications.

### Run it

```bash
aws s3 cp lambdas/sample_data/order_sample.csv \
  "s3://$(terraform -chdir=infra/terraform output -raw raw_orders_bucket)/"
```

Watch the execution in the Step Functions console, then check your inbox.

### Tear down

```bash
terraform destroy
```

S3 buckets must be empty first — `aws s3 rm s3://<bucket> --recursive` for each.

## API reference

`GET /orders` — returns the newest matching orders first.

| Parameter | Required | Notes |
|---|---|---|
| `status` | one of these two | `pending`, `processing`, `shipped`, `delivered`, `cancelled` |
| `customer_id` | one of these two | Exact match, e.g. `CUST-123` |
| `start_date` | no | `YYYY-MM-DD`, inclusive |
| `end_date` | no | `YYYY-MM-DD`, inclusive |
| `limit` | no | 1–500, default 100 |

```bash
API=$(terraform -chdir=infra/terraform output -raw orders_api_endpoint)

curl "$API?status=pending&limit=10"
curl "$API?customer_id=CUST-123&start_date=2024-01-01&end_date=2024-01-31"
```

```json
{
  "count": 2,
  "index": "status-date-index",
  "orders": [{ "order_id": "ORD-002", "total_value": 34.99, "...": "..." }],
  "has_more": false
}
```

Bad input returns `400` with an `{"error": "..."}` body.

## Querying with Athena

The export lambda writes to
`s3://<analytics-bucket>/analytics/export_date=YYYY-MM-DD/orders.json`. The Glue
crawler runs an hour later and keeps the table schema in sync.

```sql
SELECT status, COUNT(*) AS orders, SUM(total_value) AS revenue
FROM order_pipeline_analytics.analytics
WHERE export_date = current_date
GROUP BY status
ORDER BY revenue DESC;
```

Select the `order-pipeline-workgroup` workgroup in the Athena console — it caps
each query at 1 GB scanned.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Tests cover the pure logic of every lambda — validation rules, enrichment maths,
DynamoDB type conversion, archive key layout, notification rendering, and query
building. Nothing touches AWS, so the suite runs offline in about two seconds.

Every lambda folder contains a `lambda_function.py`, so `conftest.py` loads each
one under a unique module name via the `lambda_module` fixture:

```python
def test_something(lambda_module):
    save = lambda_module("save_to_dynamodb")
    ...
```

## Repository layout

```
lambdas/
  trigger_pipeline/              S3 event -> start_execution
  parse_and_validate_orders/     CSV -> validated rows
  enrich_orders/                 total_value, processed_at, pipeline_run_id
  save_to_dynamodb/              batch write to the orders table
  archive_to_s3/                 move the CSV, store processed/rejected JSON
  notify_via_sns/                success and failure emails
  export_to_s3_for_athena/       daily DynamoDB -> S3 export
  get_orders_by_status_or_date/  API Gateway handler
  step_function/                 ASL definition (rendered by Terraform)
  sample_data/                   example CSV
infra/terraform/
  main.tf        provider, buckets, DynamoDB, SQS, SNS
  lambdas.tf     functions, IAM, Step Functions, API Gateway
  analytics.tf   EventBridge, Glue, Athena
  monitoring.tf  dashboard and alarms
  variables.tf   inputs
```

## Cost

Everything is pay-per-request. Idle cost is effectively zero; the only standing
charges are S3 storage and CloudWatch log retention (14 days by default).

## License

MIT — see [LICENSE](LICENSE).
