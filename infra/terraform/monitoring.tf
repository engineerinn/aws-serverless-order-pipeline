# CloudWatch dashboard + alarms

resource "aws_cloudwatch_dashboard" "order_pipeline" {

  dashboard_name = "OrderPipelineDashboard"
  dashboard_body = jsonencode({

    widgets = [
      {
        type = "metric"
        properties = {
          title  = "Lambda Errors"
          metrics = [["AWS/Lambda", "Errors", "FunctionName", "parse_and_validate_orders"]]
          period = 300
          stat   = "Sum"
        }
      },

      {
        type = "metric"
        properties = {
          title  = "Step Function Executions"
          metrics = [["AWS/States", "ExecutionsSucceeded"], ["AWS/States", "ExecutionsFailed"]]
          period = 300

        }
      }
    ]
  })

}

# Alarm: alert if pipeline fails more than twice in 5 minutes

resource "aws_cloudwatch_metric_alarm" "pipeline_failures" {

  alarm_name          = "order-pipeline-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 2
  alarm_actions       = [aws_sns_topic.alerts.arn]

}
