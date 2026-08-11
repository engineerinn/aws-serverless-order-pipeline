# CloudWatch dashboard + alarms

resource "aws_cloudwatch_dashboard" "order_pipeline" {
  dashboard_name = "${local.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6

        properties = {
          title  = "Lambda errors by function"
          region = var.aws_region
          period = 300
          stat   = "Sum"

          metrics = [
            for key, name in local.functions :
            ["AWS/Lambda", "Errors", "FunctionName", name]
          ]
        }
      },

      {
        type   = "metric"
        width  = 12
        height = 6

        properties = {
          title  = "Lambda duration (p95)"
          region = var.aws_region
          period = 300
          stat   = "p95"

          metrics = [
            for key, name in local.functions :
            ["AWS/Lambda", "Duration", "FunctionName", name]
          ]
        }
      },

      {
        type   = "metric"
        width  = 12
        height = 6

        properties = {
          title  = "Step Function executions"
          region = var.aws_region
          period = 300
          stat   = "Sum"

          metrics = [
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", aws_sfn_state_machine.order_workflow.arn],
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", aws_sfn_state_machine.order_workflow.arn],
            ["AWS/States", "ExecutionsTimedOut", "StateMachineArn", aws_sfn_state_machine.order_workflow.arn],
          ]
        }
      },

      {
        type   = "metric"
        width  = 12
        height = 6

        properties = {
          title  = "Messages in the dead letter queue"
          region = var.aws_region
          period = 300
          stat   = "Maximum"

          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.order_dlq.name],
          ]
        }
      },
    ]
  })
}


# Alarm: alert if the pipeline fails more than twice in 5 minutes.
resource "aws_cloudwatch_metric_alarm" "pipeline_failures" {
  alarm_name          = "${local.name_prefix}-pipeline-failures"
  alarm_description   = "Order pipeline executions are failing repeatedly"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.order_workflow.arn
  }
}


# Alarm: anything landing in the DLQ means an async invoke was lost.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.name_prefix}-dlq-not-empty"
  alarm_description   = "A trigger or export invocation failed and was sent to the DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = aws_sqs_queue.order_dlq.name
  }
}
