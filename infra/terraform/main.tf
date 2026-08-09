###############################################################################
# main.tf — provider, backend, and core storage resources
###############################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # NOTE: this bucket must already exist before you run `terraform init`.
  # Create it once by hand, then uncomment this block.
  # backend "s3" {
  #   bucket       = "your-terraform-state-bucket"
  #   key          = "order-pipeline/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Used to make S3 bucket names globally unique.
data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  bucket_suffix = data.aws_caller_identity.current.account_id
}

###############################################################################
# S3 — raw order uploads
###############################################################################

resource "aws_s3_bucket" "raw_orders" {
  bucket = "${local.name_prefix}-raw-orders-${local.bucket_suffix}"
}

resource "aws_s3_bucket_public_access_block" "raw_orders" {
  bucket                  = aws_s3_bucket.raw_orders.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw_orders" {
  bucket = aws_s3_bucket.raw_orders.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_orders" {
  bucket = aws_s3_bucket.raw_orders.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


###############################################################################
# S3 — analytics exports (queried by Athena)
###############################################################################

resource "aws_s3_bucket" "analytics" {
  bucket = "${local.name_prefix}-analytics-${local.bucket_suffix}"
}

resource "aws_s3_bucket_public_access_block" "analytics" {
  bucket                  = aws_s3_bucket.analytics.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


###############################################################################
# DynamoDB — orders table
###############################################################################

resource "aws_dynamodb_table" "orders" {
  name         = "${local.name_prefix}-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  # Every attribute declared here must be used as a key somewhere below.
  attribute {
    name = "order_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "order_date"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  # Query: "all shipped orders, newest first"
  global_secondary_index {
    name            = "status-date-index"
    hash_key        = "status"
    range_key       = "order_date"
    projection_type = "ALL"
  }

  # Query: "order history for one customer"
  global_secondary_index {
    name            = "customer-date-index"
    hash_key        = "customer_id"
    range_key       = "order_date"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}


###############################################################################
# SQS — dead letter queue for failed order processing
###############################################################################

resource "aws_sqs_queue" "order_dlq" {
  name                      = "${local.name_prefix}-dlq"
  message_retention_seconds = var.dlq_retention_seconds
  sqs_managed_sse_enabled   = true
}


###############################################################################
# SNS — pipeline notifications
###############################################################################

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

# You must click the confirmation link emailed to you after the first apply.
resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}


###############################################################################
# Outputs
###############################################################################

output "raw_orders_bucket" {
  description = "Upload order CSVs here to trigger the pipeline"
  value       = aws_s3_bucket.raw_orders.bucket
}

output "analytics_bucket" {
  description = "Where daily exports land for Athena"
  value       = aws_s3_bucket.analytics.bucket
}

output "orders_table_name" {
  description = "DynamoDB orders table"
  value       = aws_dynamodb_table.orders.name
}

output "dlq_url" {
  description = "Dead letter queue URL"
  value       = aws_sqs_queue.order_dlq.url
}

output "alerts_topic_arn" {
  description = "SNS topic for pipeline alerts"
  value       = aws_sns_topic.alerts.arn
}