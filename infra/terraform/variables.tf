# Input Variables (region, environment, etc)

###############################################################################
# variables.tf — input variables for the order pipeline
###############################################################################

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project slug used as a prefix for all resource names"
  type        = string
  default     = "order-pipeline"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "project_name must be lowercase alphanumeric with hyphens only."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "alert_email" {
  description = "Email address that receives pipeline success/failure notifications"
  type        = string
  default     = "hello@rinnadia.uk"
}

variable "log_retention_days" {
  description = "How long to keep CloudWatch logs"
  type        = number
  default     = 14
}

variable "dlq_retention_seconds" {
  description = "How long failed messages stay in the dead letter queue"
  type        = number
  default     = 1209600 # 14 days
}