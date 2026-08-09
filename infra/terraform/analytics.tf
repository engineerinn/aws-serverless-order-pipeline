# Athena, EventBridge, Glue Crawler
###############################################################################
# analytics.tf
# Step 7 — Athena Analytics Layer
#
# Creates the daily export schedule, the Glue Data Catalog + crawler, and the
# Athena workgroup that lets you run SQL over the exported order data in S3.
#
# Depends on resources defined in other files (Terraform merges all .tf files
# in this directory automatically):
#   - aws_s3_bucket.analytics                      -> main.tf
#   - aws_lambda_function.export_to_s3_for_athena  -> lambdas.tf
#   - var.project_name, var.environment            -> variables.tf
###############################################################################


###############################################################################
# 1. S3 bucket for Athena query results
#    Athena must write every query's output somewhere. Keep it separate from
#    your data bucket so results don't get picked up by the Glue crawler.
###############################################################################

resource "aws_s3_bucket" "athena_results" {
  bucket = "${var.project_name}-athena-results-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    Purpose     = "athena-query-results"
  }
}

# Block all public access — query results can contain business data.
resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Query results pile up fast and cost money. Expire them after 30 days.
resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-old-query-results"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }
  }
}


###############################################################################
# 2. EventBridge — run the DynamoDB -> S3 export once a day
#    cron(minute hour day-of-month month day-of-week year)
#    "cron(0 0 * * ? *)" = every day at 00:00 UTC
###############################################################################

resource "aws_cloudwatch_event_rule" "daily_analytics_export" {
  name                = "${var.project_name}-daily-analytics-export"
  description         = "Triggers the DynamoDB to S3 analytics export every day at 00:00 UTC"
  schedule_expression = "cron(0 0 * * ? *)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_target" "daily_analytics_export" {
  rule      = aws_cloudwatch_event_rule.daily_analytics_export.name
  target_id = "export-to-s3-for-athena"
  arn       = aws_lambda_function.export_to_s3_for_athena.arn
}

# Without this, EventBridge is allowed to fire but Lambda refuses the call.
resource "aws_lambda_permission" "allow_eventbridge_invoke" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.export_to_s3_for_athena.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_analytics_export.arn
}


###############################################################################
# 3. Glue Data Catalog database
#    This is the "database" Athena queries against. It holds table metadata
#    only — the actual data stays in S3.
#
#    Note: Glue database names cannot contain hyphens, hence the replace().
###############################################################################

resource "aws_glue_catalog_database" "orders_analytics" {
  name        = "${replace(var.project_name, "-", "_")}_analytics"
  description = "Catalog database for order analytics exported from DynamoDB"
}


###############################################################################
# 4. IAM role for the Glue crawler
###############################################################################

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_crawler" {
  name               = "${var.project_name}-glue-crawler-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# AWS-managed policy covering the Glue service's own permissions.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_crawler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Scoped read access to only the analytics prefix — not the whole account.
data "aws_iam_policy_document" "glue_s3_read" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.analytics.arn,
      "${aws_s3_bucket.analytics.arn}/analytics/*",
    ]
  }
}

resource "aws_iam_role_policy" "glue_s3_read" {
  name   = "${var.project_name}-glue-s3-read"
  role   = aws_iam_role.glue_crawler.id
  policy = data.aws_iam_policy_document.glue_s3_read.json
}


###############################################################################
# 5. Glue crawler
#    Scans the exported JSON in S3, infers the schema, and creates/updates
#    the table in the catalog. Runs at 01:00 UTC — one hour after the export,
#    so it always crawls fresh data.
###############################################################################

resource "aws_glue_crawler" "orders" {
  name          = "${var.project_name}-orders-crawler"
  role          = aws_iam_role.glue_crawler.arn
  database_name = aws_glue_catalog_database.orders_analytics.name
  description   = "Infers schema for exported order data and keeps the catalog in sync"

  s3_target {
    path = "s3://${aws_s3_bucket.analytics.bucket}/analytics/"
  }

  schedule = "cron(0 1 * * ? *)"

  # LOG instead of DELETE means a bad export won't silently drop your table.
  schema_change_policy {
    delete_behavior = "LOG"
    update_behavior = "UPDATE_IN_DATABASE"
  }

  # Combine date partitions into one table rather than one table per folder.
  configuration = jsonencode({
    Version = 1.0
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
    CrawlerOutput = {
      Partitions = {
        AddOrUpdateBehavior = "InheritFromTable"
      }
    }
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }

  depends_on = [aws_iam_role_policy.glue_s3_read]
}


###############################################################################
# 6. Athena workgroup
#    Isolates this project's queries, forces the result location, and sets a
#    scan limit so a runaway query can't run up a bill.
###############################################################################

resource "aws_athena_workgroup" "orders" {
  name        = "${var.project_name}-workgroup"
  description = "Workgroup for order analytics queries"

  configuration {
    # Ignore client-side overrides — everyone uses these settings.
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    # Cost guardrail: cancel any query that would scan more than 1 GB.
    bytes_scanned_cutoff_per_query = 1073741824

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}


###############################################################################
# 7. Outputs — handy after `terraform apply`
###############################################################################

output "athena_workgroup_name" {
  description = "Athena workgroup to select in the console"
  value       = aws_athena_workgroup.orders.name
}

output "glue_database_name" {
  description = "Glue catalog database to query in Athena"
  value       = aws_glue_catalog_database.orders_analytics.name
}

output "glue_crawler_name" {
  description = "Run this manually with: aws glue start-crawler --name <value>"
  value       = aws_glue_crawler.orders.name
}

output "athena_results_bucket" {
  description = "Where Athena writes query results"
  value       = aws_s3_bucket.athena_results.bucket
}
