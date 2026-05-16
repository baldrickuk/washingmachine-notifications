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
# Secrets Manager
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.stack_name}/secrets"
  description = "Sensitive credentials — Twilio, WhatsApp tokens, and recipient PII"
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    twilio_auth_token     = var.twilio_auth_token
    whatsapp_access_token = var.whatsapp_access_token
    wife_email            = var.wife_email
    wife_phone            = var.wife_phone
  })
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
