data "aws_caller_identity" "current" {}

data "aws_kms_key" "ssm" {
  key_id = "alias/aws/ssm"
}

# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "reminders" {
  name         = "${var.stack_name}-reminders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"

  attribute {
    name = "PK"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

# ---------------------------------------------------------------------------
# SSM Parameter Store (SecureString) — sensitive credentials
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "pushover_app_token" {
  name  = "/${var.stack_name}/pushover_app_token"
  type  = "SecureString"
  value = var.pushover_app_token

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "pushover_user_key" {
  name  = "/${var.stack_name}/pushover_user_key"
  type  = "SecureString"
  value = var.pushover_user_key

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "origin_verify_token" {
  count = var.origin_verify_token != "" ? 1 : 0

  name  = "/${var.stack_name}/origin_verify_token"
  type  = "SecureString"
  value = var.origin_verify_token

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "wife_email" {
  name  = "/${var.stack_name}/wife_email"
  type  = "SecureString"
  value = var.wife_email

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "wife_phone" {
  name  = "/${var.stack_name}/wife_phone"
  type  = "SecureString"
  value = var.wife_phone

  lifecycle {
    ignore_changes = [value]
  }
}

# ---------------------------------------------------------------------------
# SQS Dead Letter Queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.stack_name}-dlq"
  message_retention_seconds = 1209600 # 14 days
}

# ---------------------------------------------------------------------------
# SNS Alert Topic
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${var.stack_name}-alerts"
}

resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
