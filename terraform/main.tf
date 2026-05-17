data "aws_caller_identity" "current" {}

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

resource "aws_ssm_parameter" "twilio_auth_token" {
  name  = "/${var.stack_name}/twilio_auth_token"
  type  = "SecureString"
  value = var.twilio_auth_token

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "whatsapp_access_token" {
  count = var.whatsapp_access_token != "" ? 1 : 0

  name  = "/${var.stack_name}/whatsapp_access_token"
  type  = "SecureString"
  value = var.whatsapp_access_token

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
