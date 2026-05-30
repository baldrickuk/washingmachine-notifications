# ---------------------------------------------------------------------------
# CloudWatch Dashboard (OE-6)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.stack_name

  dashboard_body = jsonencode({
    start = "-PT24H"
    widgets = [
      # Row 1 — Lambda invocations, errors, duration
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "Lambda — Invocations"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.send_weekly_email.function_name, { label = "WeeklyEmail" }],
            [".", ".", ".", aws_lambda_function.send_daily_sms.function_name, { label = "DailySMS" }],
            [".", ".", ".", aws_lambda_function.confirm_task.function_name, { label = "ConfirmTask" }],
            [".", ".", ".", aws_lambda_function.verify_delivery.function_name, { label = "VerifyDelivery" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "Lambda — Errors"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.send_weekly_email.function_name, { label = "WeeklyEmail", color = "#d62728" }],
            [".", ".", ".", aws_lambda_function.send_daily_sms.function_name, { label = "DailySMS", color = "#ff7f0e" }],
            [".", ".", ".", aws_lambda_function.confirm_task.function_name, { label = "ConfirmTask", color = "#e377c2" }],
            [".", ".", ".", aws_lambda_function.verify_delivery.function_name, { label = "VerifyDelivery", color = "#8c564b" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "Lambda — Duration p99 (ms)"
          view    = "timeSeries"
          stacked = false
          stat    = "p99"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.send_weekly_email.function_name, { label = "WeeklyEmail" }],
            [".", ".", ".", aws_lambda_function.send_daily_sms.function_name, { label = "DailySMS" }],
            [".", ".", ".", aws_lambda_function.confirm_task.function_name, { label = "ConfirmTask" }],
            [".", ".", ".", aws_lambda_function.verify_delivery.function_name, { label = "VerifyDelivery" }],
          ]
        }
      },
      # Row 2 — DynamoDB, API Gateway, SQS
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "DynamoDB — Requests"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "SuccessfulRequestLatency", "TableName", aws_dynamodb_table.reminders.name, "Operation", "GetItem", { label = "GetItem" }],
            [".", ".", ".", ".", ".", "PutItem", { label = "PutItem" }],
            [".", ".", ".", ".", ".", "UpdateItem", { label = "UpdateItem" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "API Gateway — Requests & 4xx"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.confirm.id, { label = "Requests" }],
            ["AWS/ApiGateway", "4xx", "ApiId", aws_apigatewayv2_api.confirm.id, { label = "4xx Errors", color = "#ff7f0e" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "SQS DLQ — Messages Visible"
          view    = "timeSeries"
          stacked = false
          stat    = "Maximum"
          period  = 60
          region  = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.dlq.name, { label = "DLQ Depth", color = "#d62728" }],
          ]
        }
      },
      # Row 3 — Lambda throttles + concurrency
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "Lambda — Throttles"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          region  = var.aws_region
          metrics = [
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.send_weekly_email.function_name, { label = "WeeklyEmail", color = "#d62728" }],
            [".", ".", ".", aws_lambda_function.send_daily_sms.function_name, { label = "DailySMS", color = "#ff7f0e" }],
            [".", ".", ".", aws_lambda_function.confirm_task.function_name, { label = "ConfirmTask", color = "#e377c2" }],
            [".", ".", ".", aws_lambda_function.verify_delivery.function_name, { label = "VerifyDelivery", color = "#8c564b" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "Lambda — Concurrent Executions"
          view    = "timeSeries"
          stacked = true
          stat    = "Maximum"
          period  = 60
          region  = var.aws_region
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.send_weekly_email.function_name, { label = "WeeklyEmail" }],
            [".", ".", ".", aws_lambda_function.send_daily_sms.function_name, { label = "DailySMS" }],
            [".", ".", ".", aws_lambda_function.confirm_task.function_name, { label = "ConfirmTask" }],
            [".", ".", ".", aws_lambda_function.verify_delivery.function_name, { label = "VerifyDelivery" }],
          ]
        }
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch Alarms
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "weekly_email_errors" {
  alarm_name          = "${var.stack_name}-weekly-email-errors"
  alarm_description   = "SendWeeklyEmail Lambda has errors — Sunday reminder may not have been sent"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.send_weekly_email.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "daily_sms_errors" {
  alarm_name          = "${var.stack_name}-daily-sms-errors"
  alarm_description   = "SendDailySMS Lambda has errors — a daily reminder may not have been sent"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.send_daily_sms.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "confirm_task_errors" {
  alarm_name          = "${var.stack_name}-confirm-task-errors"
  alarm_description   = "ConfirmTask Lambda has errors — a confirmation attempt may have failed"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.confirm_task.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${var.stack_name}-dlq-depth"
  alarm_description   = "Lambda DLQ is non-empty — a function failed after all retries"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_throttling" {
  alarm_name          = "${var.stack_name}-api-throttling"
  alarm_description   = "API Gateway returning 4xx — rate limit may be hit (CloudFront throttling)"
  namespace           = "AWS/ApiGateway"
  metric_name         = "4xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.confirm.id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# CloudTrail — DynamoDB data events (SEC-5)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "trail" {
  bucket = "${var.stack_name}-audit-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "trail" {
  bucket = aws_s3_bucket.trail.id

  rule {
    id     = "expire-after-90-days"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

data "aws_iam_policy_document" "trail_bucket" {
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail.arn]
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.trail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id
  policy = data.aws_iam_policy_document.trail_bucket.json
}

resource "aws_cloudtrail" "app" {
  name                          = "${var.stack_name}-trail"
  s3_bucket_name                = aws_s3_bucket.trail.id
  enable_logging                = true
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = false

    data_resource {
      type   = "AWS::DynamoDB::Table"
      values = [aws_dynamodb_table.reminders.arn]
    }
  }

  depends_on = [aws_s3_bucket_policy.trail]
}
