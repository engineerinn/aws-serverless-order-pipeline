# Lambda functions + IAM roles
###############################################################################
# lambdas.tf
#
# Everything that runs code, plus the wiring that connects it:
#   1. shared settings         — runtime, paths, the folder -> function map
#   2. packaging               — zips each lambdas/<folder>/ at plan time
#   3. IAM                     — one role per function, least privilege
#   4. log groups              — so retention is managed, not "never expire"
#   5. the eight functions     — declared explicitly, see the note in section 5
#   6. the S3 trigger          — a .csv upload starts the pipeline
#   7. the state machine       — renders order_workflow.asl.json
#   8. the query API           — GET /orders behind an API key
#
# Depends on resources defined in other files (Terraform merges all .tf files
# in this directory automatically):
#   - aws_s3_bucket.raw_orders / .archive / .analytics  -> main.tf
#   - aws_dynamodb_table.orders                         -> main.tf
#   - aws_sns_topic.alerts                              -> main.tf
#   - local.name_prefix, var.log_retention_days         -> main.tf, variables.tf
###############################################################################


###############################################################################
# 1. Shared settings
#
#    local.functions maps "source folder under lambdas/" -> "deployed name".
#    It drives packaging, IAM roles and log groups below, so adding a ninth
#    lambda means adding one line here plus one aws_lambda_function resource.
###############################################################################

locals {
  lambda_runtime = "python3.12"
  lambda_source  = "${path.module}/../../lambdas"
  build_dir      = "${path.module}/.build"

  functions = {
    trigger_pipeline             = "${local.name_prefix}-trigger-pipeline"
    parse_and_validate_orders    = "${local.name_prefix}-parse-and-validate-orders"
    enrich_orders                = "${local.name_prefix}-enrich-orders"
    save_to_dynamodb             = "${local.name_prefix}-save-to-dynamodb"
    archive_to_s3                = "${local.name_prefix}-archive-to-s3"
    notify_via_sns               = "${local.name_prefix}-notify-via-sns"
    export_to_s3_for_athena      = "${local.name_prefix}-export-to-s3-for-athena"
    get_orders_by_status_or_date = "${local.name_prefix}-get-orders"
  }
}


###############################################################################
# 2. Packaging
#
#    There is no separate build step: Terraform zips each folder itself during
#    `plan`. Test files and __pycache__ are excluded so that running pytest
#    does not change source_code_hash and force a pointless redeploy.
###############################################################################

data "archive_file" "lambda" {
  for_each = local.functions

  type        = "zip"
  source_dir  = "${local.lambda_source}/${each.key}"
  output_path = "${local.build_dir}/${each.key}.zip"
  excludes    = ["test_lambda_function.py", "__pycache__"]
}


###############################################################################
# 3. IAM — one role per function
#
#    Every function gets the same trust policy (only Lambda may assume it) and
#    the AWS-managed basic execution policy (permission to write its own logs).
#    Anything beyond that is granted per function in local.function_policies.
###############################################################################

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.functions

  name               = "${each.value}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each = local.functions

  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# enrich_orders is deliberately absent: it is pure computation and touches no
# AWS service, so logging permission is all it needs.
locals {
  function_policies = {
    # Invoked asynchronously by S3, so a failure has no caller to report to —
    # hence the dead letter queue, and the permission to write to it.
    trigger_pipeline = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["states:StartExecution"]
          Resource = [aws_sfn_state_machine.order_workflow.arn]
        },
        {
          Effect   = "Allow"
          Action   = ["sqs:SendMessage"]
          Resource = [aws_sqs_queue.order_dlq.arn]
        },
      ]
    })

    parse_and_validate_orders = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.raw_orders.arn}/*"]
      }]
    })

    save_to_dynamodb = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:BatchWriteItem"]
        Resource = [aws_dynamodb_table.orders.arn]
      }]
    })

    # Reads and deletes the source CSV in the landing bucket, writes the copy
    # and the processed/rejected JSON into the archive bucket.
    archive_to_s3 = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:DeleteObject"]
          Resource = ["${aws_s3_bucket.raw_orders.arn}/*"]
        },
        {
          Effect   = "Allow"
          Action   = ["s3:PutObject"]
          Resource = ["${aws_s3_bucket.archive.arn}/*"]
        },
      ]
    })

    notify_via_sns = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      }]
    })

    export_to_s3_for_athena = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect   = "Allow"
          Action   = ["dynamodb:Scan"]
          Resource = [aws_dynamodb_table.orders.arn]
        },
        {
          Effect   = "Allow"
          Action   = ["s3:PutObject"]
          Resource = ["${aws_s3_bucket.analytics.arn}/*"]
        },
        {
          Effect   = "Allow"
          Action   = ["sqs:SendMessage"]
          Resource = [aws_sqs_queue.order_dlq.arn]
        },
      ]
    })

    # Query, not Scan — and the index ARNs, because querying a GSI needs
    # permission on the index itself as well as on the table.
    get_orders_by_status_or_date = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect = "Allow"
        Action = ["dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.orders.arn,
          "${aws_dynamodb_table.orders.arn}/index/*",
        ]
      }]
    })
  }
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.function_policies

  name   = "${local.functions[each.key]}-policy"
  role   = aws_iam_role.lambda[each.key].id
  policy = each.value
}


###############################################################################
# 4. Log groups
#
#    Lambda creates these on its own if they are missing, but then they keep
#    logs forever. Declaring them here puts retention under Terraform's
#    control. Each function depends on its log group so the retention setting
#    is in place before the function can ever be invoked.
###############################################################################

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.functions

  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.log_retention_days
}


###############################################################################
# 5. The eight functions
#
#    These are written out one by one rather than with a single for_each.
#    trigger_pipeline needs the state machine ARN, and the state machine needs
#    five of the other functions. With one for_each resource that would be a
#    cycle at the resource level, even though no individual function actually
#    depends on itself.
#
#    Timeouts are set just under the TimeoutSeconds in order_workflow.asl.json
#    so that a slow function fails as a Lambda timeout (which Step Functions
#    retries) rather than as a state timeout (which it does not).
###############################################################################

resource "aws_lambda_function" "parse_and_validate_orders" {
  function_name = local.functions["parse_and_validate_orders"]
  role          = aws_iam_role.lambda["parse_and_validate_orders"].arn

  filename         = data.archive_file.lambda["parse_and_validate_orders"].output_path
  source_code_hash = data.archive_file.lambda["parse_and_validate_orders"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 120
  memory_size = 512

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "enrich_orders" {
  function_name = local.functions["enrich_orders"]
  role          = aws_iam_role.lambda["enrich_orders"].arn

  filename         = data.archive_file.lambda["enrich_orders"].output_path
  source_code_hash = data.archive_file.lambda["enrich_orders"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 60
  memory_size = 256

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "save_to_dynamodb" {
  function_name = local.functions["save_to_dynamodb"]
  role          = aws_iam_role.lambda["save_to_dynamodb"].arn

  filename         = data.archive_file.lambda["save_to_dynamodb"].output_path
  source_code_hash = data.archive_file.lambda["save_to_dynamodb"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 120
  memory_size = 256

  environment {
    variables = {
      ORDERS_TABLE = aws_dynamodb_table.orders.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "archive_to_s3" {
  function_name = local.functions["archive_to_s3"]
  role          = aws_iam_role.lambda["archive_to_s3"].arn

  filename         = data.archive_file.lambda["archive_to_s3"].output_path
  source_code_hash = data.archive_file.lambda["archive_to_s3"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 60
  memory_size = 256

  environment {
    variables = {
      ARCHIVE_BUCKET = aws_s3_bucket.archive.bucket

      # Set to "false" to leave the CSV in the landing bucket after a run.
      DELETE_SOURCE_OBJECT = "true"
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "notify_via_sns" {
  function_name = local.functions["notify_via_sns"]
  role          = aws_iam_role.lambda["notify_via_sns"].arn

  filename         = data.archive_file.lambda["notify_via_sns"].output_path
  source_code_hash = data.archive_file.lambda["notify_via_sns"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      SNS_TOPIC    = aws_sns_topic.alerts.arn
      PROJECT_NAME = var.project_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# Started by the S3 upload notification, not by the state machine.
resource "aws_lambda_function" "trigger_pipeline" {
  function_name = local.functions["trigger_pipeline"]
  role          = aws_iam_role.lambda["trigger_pipeline"].arn

  filename         = data.archive_file.lambda["trigger_pipeline"].output_path
  source_code_hash = data.archive_file.lambda["trigger_pipeline"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      STEP_FUNCTION_ARN = aws_sfn_state_machine.order_workflow.arn
    }
  }

  # S3 invokes this asynchronously: nobody is waiting on the response, so a
  # failure would vanish silently. Instead the event lands in the DLQ, and the
  # alarm in monitoring.tf emails you.
  dead_letter_config {
    target_arn = aws_sqs_queue.order_dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# Run once a day by the EventBridge rule in analytics.tf.
resource "aws_lambda_function" "export_to_s3_for_athena" {
  function_name = local.functions["export_to_s3_for_athena"]
  role          = aws_iam_role.lambda["export_to_s3_for_athena"].arn

  filename         = data.archive_file.lambda["export_to_s3_for_athena"].output_path
  source_code_hash = data.archive_file.lambda["export_to_s3_for_athena"].output_base64sha256

  handler = "lambda_function.lambda_handler"
  runtime = local.lambda_runtime

  # A full table scan of a growing table is the slowest thing here.
  timeout     = 300
  memory_size = 512

  environment {
    variables = {
      ORDERS_TABLE     = aws_dynamodb_table.orders.name
      ANALYTICS_BUCKET = aws_s3_bucket.analytics.bucket

      # Must match the s3_target path on the Glue crawler in analytics.tf.
      EXPORT_PREFIX = "analytics"
    }
  }

  # Also an async invoke (EventBridge), so the same reasoning applies.
  dead_letter_config {
    target_arn = aws_sqs_queue.order_dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# Sits behind API Gateway, outside the state machine.
resource "aws_lambda_function" "get_orders_by_status_or_date" {
  function_name = local.functions["get_orders_by_status_or_date"]
  role          = aws_iam_role.lambda["get_orders_by_status_or_date"].arn

  filename         = data.archive_file.lambda["get_orders_by_status_or_date"].output_path
  source_code_hash = data.archive_file.lambda["get_orders_by_status_or_date"].output_base64sha256

  handler     = "lambda_function.lambda_handler"
  runtime     = local.lambda_runtime
  timeout     = 30
  memory_size = 256

  environment {
    variables = {
      ORDERS_TABLE = aws_dynamodb_table.orders.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}


###############################################################################
# 6. The S3 trigger
#
#    Two halves that are easy to confuse: aws_lambda_permission lets S3 call
#    the function, aws_s3_bucket_notification tells S3 to actually do it.
#    Miss the permission and uploads silently do nothing.
#
#    The suffix filter matters — without it, the JSON files that archive_to_s3
#    writes would look like new work to be done.
###############################################################################

resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_pipeline.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_orders.arn
}

resource "aws_s3_bucket_notification" "raw_orders" {
  bucket = aws_s3_bucket.raw_orders.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.trigger_pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}


###############################################################################
# 7. The state machine
#
#    order_workflow.asl.json is a template: templatefile() substitutes the five
#    ${...LambdaArn} placeholders with the real ARNs at plan time.
###############################################################################

data "aws_iam_policy_document" "step_functions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${local.name_prefix}-workflow-role"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume_role.json
}

# The state machine may invoke exactly these five functions and nothing else.
resource "aws_iam_role_policy" "step_functions_invoke" {
  name = "${local.name_prefix}-workflow-invoke"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["lambda:InvokeFunction"]
      Resource = [
        aws_lambda_function.parse_and_validate_orders.arn,
        aws_lambda_function.enrich_orders.arn,
        aws_lambda_function.save_to_dynamodb.arn,
        aws_lambda_function.archive_to_s3.arn,
        aws_lambda_function.notify_via_sns.arn,
      ]
    }]
  })
}

resource "aws_sfn_state_machine" "order_workflow" {
  name     = "${local.name_prefix}-order-workflow"
  role_arn = aws_iam_role.step_functions.arn

  definition = templatefile("${local.lambda_source}/step_function/order_workflow.asl.json", {
    ParseLambdaArn   = aws_lambda_function.parse_and_validate_orders.arn
    EnrichLambdaArn  = aws_lambda_function.enrich_orders.arn
    SaveLambdaArn    = aws_lambda_function.save_to_dynamodb.arn
    ArchiveLambdaArn = aws_lambda_function.archive_to_s3.arn
    NotifyLambdaArn  = aws_lambda_function.notify_via_sns.arn
  })

  depends_on = [aws_iam_role_policy.step_functions_invoke]
}


###############################################################################
# 8. The query API — GET /orders
#
#    A REST API rather than the cheaper HTTP API, because API keys and usage
#    plans are a REST-API feature. The key is not real security (it is a shared
#    secret, not a user identity) but it keeps the endpoint off the open
#    internet and gives you a rate limit and a quota.
#
#    AWS_PROXY integration hands the lambda the whole request, which is why the
#    handler reads event["queryStringParameters"] and returns {statusCode, body}.
###############################################################################

resource "aws_api_gateway_rest_api" "orders" {
  name        = "${local.name_prefix}-orders-api"
  description = "Read-only query endpoint over the orders table"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "orders" {
  rest_api_id = aws_api_gateway_rest_api.orders.id
  parent_id   = aws_api_gateway_rest_api.orders.root_resource_id
  path_part   = "orders"
}

resource "aws_api_gateway_method" "get_orders" {
  rest_api_id = aws_api_gateway_rest_api.orders.id
  resource_id = aws_api_gateway_resource.orders.id
  http_method = "GET"

  # "NONE" refers to IAM/Cognito authorization; the API key is separate.
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "get_orders" {
  rest_api_id = aws_api_gateway_rest_api.orders.id
  resource_id = aws_api_gateway_resource.orders.id
  http_method = aws_api_gateway_method.get_orders.http_method

  type = "AWS_PROXY"

  # Always POST — that is how API Gateway calls Lambda internally, regardless
  # of the method the client used.
  integration_http_method = "POST"
  uri                     = aws_lambda_function.get_orders_by_status_or_date.invoke_arn
}

resource "aws_lambda_permission" "allow_apigateway_invoke" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_orders_by_status_or_date.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.orders.execution_arn}/*/GET/orders"
}

# A REST API only serves traffic once a deployment is published to a stage.
# The triggers hash forces a fresh deployment whenever the route changes;
# without it, edits apply to the config but never reach the live URL.
resource "aws_api_gateway_deployment" "orders" {
  rest_api_id = aws_api_gateway_rest_api.orders.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.orders.id,
      aws_api_gateway_method.get_orders.id,
      aws_api_gateway_integration.get_orders.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.orders.id
  deployment_id = aws_api_gateway_deployment.orders.id
  stage_name    = "prod"
}

resource "aws_api_gateway_api_key" "orders" {
  name    = "${local.name_prefix}-orders-api-key"
  enabled = true
}

# An API key does nothing on its own — it only grants access to the stages
# listed in a usage plan it belongs to.
resource "aws_api_gateway_usage_plan" "orders" {
  name        = "${local.name_prefix}-orders-usage-plan"
  description = "Rate limit and quota for the orders query endpoint"

  api_stages {
    api_id = aws_api_gateway_rest_api.orders.id
    stage  = aws_api_gateway_stage.prod.stage_name
  }

  throttle_settings {
    rate_limit  = 10
    burst_limit = 20
  }

  quota_settings {
    limit  = 10000
    period = "MONTH"
  }
}

resource "aws_api_gateway_usage_plan_key" "orders" {
  key_id        = aws_api_gateway_api_key.orders.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.orders.id
}


###############################################################################
# 9. Outputs
###############################################################################

output "state_machine_arn" {
  description = "Step Functions state machine that runs the pipeline"
  value       = aws_sfn_state_machine.order_workflow.arn
}

output "orders_api_endpoint" {
  description = "GET this with an x-api-key header"
  value       = "${aws_api_gateway_stage.prod.invoke_url}/orders"
}

output "orders_api_key" {
  description = "Read with: terraform output -raw orders_api_key"
  value       = aws_api_gateway_api_key.orders.value
  sensitive   = true
}
