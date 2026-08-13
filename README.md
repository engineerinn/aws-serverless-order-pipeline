# AWS Serverless Order Processing Pipeline

**English** · [한국어](README.ko.md)

[![CI](https://github.com/engineerinn/aws-serverless-order-pipeline/actions/workflows/deploy.yml/badge.svg)](https://github.com/engineerinn/aws-serverless-order-pipeline/actions/workflows/deploy.yml)
![Terraform](https://img.shields.io/badge/Terraform-%3E%3D1.6-7B42BC)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![Tests](https://img.shields.io/badge/tests-70%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Drop a CSV of orders into S3. The pipeline validates every row, enriches it, persists it to DynamoDB, archives the file, and emails you the outcome — then exports the table to S3 once a day so you can query it in Athena with SQL.

Entirely serverless, entirely defined in Terraform, deployed by GitHub Actions with no long-lived AWS keys anywhere.

---

## At a glance

| | |
|---|---|
| **Problem** | Batch order files need validation, enrichment, storage, and analytics — without a server to babysit. |
| **Approach** | Event-driven pipeline: S3 → Lambda → Step Functions → DynamoDB → S3 → SNS, plus a daily analytics export and a query API. |
| **Stack** | Python 3.12 · Terraform · Step Functions · Lambda · DynamoDB · S3 · SNS · SQS · EventBridge · API Gateway · Glue · Athena · CloudWatch |
| **Scale** | 8 Lambdas, 5-state workflow, 4 Terraform modules-worth of config, 70 unit tests |
| **CI/CD** | GitHub Actions — tests + `terraform validate` on every PR, OIDC-authenticated apply on merge to `main` |
| **Idle cost** | ~$0. Everything is pay-per-request; only S3 storage and 14-day log retention accrue. |

---

## Architecture

![Solution architecture](solution_architecture_diagram.png)

```
CSV upload to S3 (raw-orders bucket, .csv filter)
      │
      ▼
trigger_pipeline ──start_execution──▶ Step Functions
                                          │
   ┌──────────────┬───────────────┬───────┴────────┬────────────────┐
   ▼              ▼               ▼                ▼                ▼
ParseAndValidate  EnrichOrders  SaveToDynamoDB  ArchiveToS3   NotifySuccess
 CSV → rows       totals, IDs   orders table    archive bkt    SNS email

   any States.ALL error ──▶ NotifyFailure ──▶ PipelineFailed

Side paths (outside the state machine)
   EventBridge (daily 00:00 UTC) ──▶ export_to_s3_for_athena ──▶ S3 + Glue + Athena
   API Gateway GET /orders       ──▶ get_orders_by_status_or_date ──▶ DynamoDB GSIs
```

### Why it's built this way

These are the decisions that took the most thought — each one is a bug that would have shipped otherwise.

**The archive bucket is separate from the landing bucket.**
Writing archives back into the bucket that triggers the pipeline would make it consume its own output — an infinite loop billed by the invocation. Two buckets, plus an `.csv` suffix filter on the notification, makes that structurally impossible rather than merely unlikely.

**`archive_to_s3` returns a trimmed event.**
Step Functions caps state payloads at 256 KB. The row arrays are dropped before the final transition so a large file can't fail the pipeline at the very last step, after all the real work succeeded. `summary` survives the trim because the ASL's `Parameters` block reads `$.summary`.

**One IAM role per Lambda, and `enrich_orders` gets none beyond logging.**
Each function's policy names only the resources it actually touches. `enrich_orders` is pure computation — it reads the event, does arithmetic, returns. Giving it a table policy "for consistency" would be granting access nothing needs.

**Lambdas are declared explicitly, not with `for_each`.**
`trigger_pipeline` depends on the state machine, which depends on five other functions. A single `for_each` resource would collapse that into a resource-level dependency cycle that Terraform can't plan.

**Numbers go into DynamoDB through `Decimal(str(v))`.**
DynamoDB rejects native floats. Converting via `str` rather than `Decimal(float)` avoids inheriting binary floating-point noise into stored prices.

**The Athena export is newline-delimited JSON, not a JSON array.**
Athena's JSON SerDe parses one object per line. Integral `Decimal`s are cast back to `int` so Glue infers `bigint` instead of `string`.

**Every task has retries; the workflow has a catch-all.**
Transient Lambda errors retry with backoff. Anything else routes to `NotifyFailure → PipelineFailed`, so a failure always produces an email rather than a silent stall.

**CI deploys with OIDC, not access keys.**
GitHub Actions exchanges a short-lived OIDC token for temporary AWS credentials. No static secret exists to leak or rotate. The deploy role is provisioned by a separate `bootstrap/` root module so the pipeline never has permission to widen its own permissions in the same apply.

---

## AWS services and their role here

| Service | What it does in this project |
|---|---|
| **S3** | Three buckets: `raw-orders` (landing zone, triggers the pipeline), `archive` (date-partitioned CSV + processed/rejected JSON), `analytics` (daily export for Athena). |
| **Lambda** | Eight Python 3.12 functions — five workflow steps, one S3 trigger, one daily exporter, one API handler. |
| **Step Functions** | Orchestrates the five workflow steps with per-task retries, backoff, and a `States.ALL` failure branch. Defined in ASL, rendered by Terraform `templatefile()`. |
| **DynamoDB** | `orders` table, hash key `order_id`, plus `status-date-index` and `customer-date-index` GSIs that back the query API. |
| **SQS** | Dead letter queue for the two asynchronously invoked Lambdas, so a failed async invoke is captured instead of lost. 14-day retention. |
| **SNS** | Email notification on pipeline success and failure. |
| **EventBridge** | Daily 00:00 UTC schedule that fires the analytics export. |
| **API Gateway** | REST API exposing `GET /orders`, API-key protected, throttled to 10 rps / 20 burst with a 10,000-request monthly quota. |
| **Glue** | Catalog database plus a crawler (01:00 UTC) that keeps the Athena table schema in sync with the exported data. |
| **Athena** | SQL over the exported orders. A dedicated workgroup caps every query at 1 GB scanned so a stray `SELECT *` can't run up a bill. |
| **CloudWatch** | Log groups per function (14-day retention), a dashboard built by iterating `local.functions`, and alarms on `ExecutionsFailed > 2` and DLQ depth `> 0`. |
| **IAM** | One least-privilege execution role per Lambda, plus an OIDC-assumable deploy role for GitHub Actions. |

### Infrastructure as Code — Terraform

Every resource above is declared in `infra/terraform/`; nothing was created by hand in the console. That means the whole stack can be destroyed and recreated identically, reviewed as a diff in a pull request, and validated in CI before it ever reaches AWS.

Lambda packaging is handled by `data.archive_file` at plan time — there is no separate build step. Test files and `__pycache__` are excluded from the zips, so running the test suite doesn't change `source_code_hash` and force a spurious redeploy.

### CI/CD — GitHub Actions

`.github/workflows/deploy.yml` runs three jobs:

1. **Unit tests** — `pytest` across all eight Lambdas.
2. **Terraform validate** — `fmt -check -recursive`, then `init -backend=false && validate` for both the main config and the `bootstrap/` root module.
3. **Apply** — only on push to `main`, gated behind a protected `production` environment, authenticated by OIDC.

Pull requests run steps 1 and 2 only. Nothing reaches AWS without passing both.

---

## Features

- Row-level CSV validation with a typed rejection reason for every bad row
- Orchestrated workflow with per-step retries, backoff, and a catch-all failure branch
- One IAM role per Lambda, each scoped to the resources it actually touches
- Dead letter queue for the two asynchronously invoked functions
- Date-partitioned archive with lifecycle tiering — Standard-IA at 30 days, Glacier IR at 90
- Daily Athena export as newline-delimited JSON, Hive-partitioned by date
- Query API over the DynamoDB GSIs — by status or by customer, with an optional date range
- CloudWatch dashboard plus alarms on execution failures and DLQ depth
- 70 unit tests, no AWS calls, running in about two seconds on every push

---

## Getting started

### Prerequisites

- Terraform >= 1.6, Python 3.12
- AWS credentials with permission to create the resources above

### Deploy

```bash
cd infra/terraform
terraform init
terraform apply -var="alert_email=you@example.com"
```

Default region is `ap-southeast-2`; override with `-var="aws_region=..."`.

After the first apply, **confirm the SNS subscription email** — AWS will not send notifications until you click the link.

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

---

## API reference

`GET /orders` — newest matching orders first. **Requires an `x-api-key` header.**

| Parameter | Required | Notes |
|---|---|---|
| `status` | one of these two | `pending`, `processing`, `shipped`, `delivered`, `cancelled` |
| `customer_id` | one of these two | Exact match, e.g. `CUST-123` |
| `start_date` | no | `YYYY-MM-DD`, inclusive |
| `end_date` | no | `YYYY-MM-DD`, inclusive |
| `limit` | no | 1–500, default 100 |

```bash
API=$(terraform -chdir=infra/terraform output -raw orders_api_endpoint)
KEY=$(terraform -chdir=infra/terraform output -raw orders_api_key)

curl -H "x-api-key: $KEY" "$API?status=pending&limit=10"
curl -H "x-api-key: $KEY" "$API?customer_id=CUST-123&start_date=2024-01-01&end_date=2024-01-31"
```

```json
{
  "count": 2,
  "index": "status-date-index",
  "orders": [{ "order_id": "ORD-002", "total_value": 34.99, "...": "..." }],
  "has_more": false
}
```

Anything the caller can fix returns `400` with an `{"error": "..."}` body. A missing or invalid key returns `403`.

---

## Querying with Athena

The export Lambda writes to `s3://<analytics-bucket>/analytics/export_date=YYYY-MM-DD/orders.json`. The Glue crawler runs an hour later and keeps the table schema in sync.

```sql
SELECT status, COUNT(*) AS orders, SUM(total_value) AS revenue
FROM order_pipeline_analytics.analytics
WHERE export_date = current_date
GROUP BY status
ORDER BY revenue DESC;
```

Select the `order-pipeline-workgroup` workgroup in the Athena console — it caps each query at 1 GB scanned.

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

70 tests, no AWS calls, no `moto` — about two seconds offline. They cover the pure logic of every Lambda: validation rules, enrichment arithmetic, DynamoDB type conversion, archive key layout, notification rendering, and query building.

Every Lambda folder contains a file named `lambda_function.py`, so a plain `import lambda_function` would resolve to whichever one Python cached first and tests would silently exercise the wrong module. `conftest.py` solves this with a `lambda_module` fixture that loads each file under a unique module name:

```python
def test_something(lambda_module):
    save = lambda_module("save_to_dynamodb")
    ...
```

`pytest.ini` sets `--import-mode=importlib` so the eight identically-named `test_lambda_function.py` files don't collide either.

---

## Repository layout

```
lambdas/
  trigger_pipeline/              S3 event → start_execution
  parse_and_validate_orders/     CSV → validated rows
  enrich_orders/                 total_value, processed_at, pipeline_run_id
  save_to_dynamodb/              batch write to the orders table
  archive_to_s3/                 move the CSV, store processed/rejected JSON
  notify_via_sns/                success and failure emails
  export_to_s3_for_athena/       daily DynamoDB → S3 export
  get_orders_by_status_or_date/  API Gateway handler
  step_function/                 ASL definition (rendered by Terraform)
  sample_data/                   example CSV
infra/terraform/
  main.tf        provider, buckets, DynamoDB, SQS, SNS
  lambdas.tf     functions, IAM, Step Functions, API Gateway
  analytics.tf   EventBridge, Glue, Athena
  monitoring.tf  dashboard and alarms
  variables.tf   inputs
  bootstrap/     OIDC provider and deploy role (applied separately, once)
.github/workflows/
  deploy.yml     test → validate → apply
```

---

## Cost

Everything is pay-per-request, so idle cost is effectively zero. The only standing charges are S3 storage — tiered down to Glacier IR after 90 days — and CloudWatch log retention, capped at 14 days.

---

## License

MIT — see [LICENSE](LICENSE).
