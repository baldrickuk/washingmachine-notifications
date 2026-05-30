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

# ---------------------------------------------------------------------------
# SendWeeklyEmail — DynamoDB(Get/Put/Delete) + SES + SSM/KMS + SQS DLQ
# ---------------------------------------------------------------------------

resource "aws_iam_role" "send_weekly_email" {
  name               = "${var.stack_name}-send-weekly-email"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "send_weekly_email_basic" {
  role       = aws_iam_role.send_weekly_email.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "send_weekly_email" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.reminders.arn]
  }
  statement {
    sid     = "SES"
    effect  = "Allow"
    actions = ["ses:SendEmail"]
    resources = ["arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.from_email}"]
  }
  statement {
    sid     = "SSMParameters"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "kms:Decrypt"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.stack_name}/*",
      data.aws_kms_key.ssm.arn,
    ]
  }
  statement {
    sid     = "DLQ"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "send_weekly_email" {
  name   = "${var.stack_name}-send-weekly-email"
  role   = aws_iam_role.send_weekly_email.id
  policy = data.aws_iam_policy_document.send_weekly_email.json
}

# ---------------------------------------------------------------------------
# SendDailySMS — DynamoDB(Get/Update) + SSM/KMS + SQS DLQ
# ---------------------------------------------------------------------------

resource "aws_iam_role" "send_daily_sms" {
  name               = "${var.stack_name}-send-daily-sms"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "send_daily_sms_basic" {
  role       = aws_iam_role.send_daily_sms.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "send_daily_sms" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.reminders.arn]
  }
  statement {
    sid     = "SSMParameters"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "kms:Decrypt"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.stack_name}/*",
      data.aws_kms_key.ssm.arn,
    ]
  }
  statement {
    sid     = "DLQ"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "send_daily_sms" {
  name   = "${var.stack_name}-send-daily-sms"
  role   = aws_iam_role.send_daily_sms.id
  policy = data.aws_iam_policy_document.send_daily_sms.json
}

# ---------------------------------------------------------------------------
# ConfirmTask — DynamoDB(Get/Update) + SES + SSM/KMS
# ---------------------------------------------------------------------------

resource "aws_iam_role" "confirm_task" {
  name               = "${var.stack_name}-confirm-task"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "confirm_task_basic" {
  role       = aws_iam_role.confirm_task.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "confirm_task" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.reminders.arn]
  }
  statement {
    sid     = "SES"
    effect  = "Allow"
    actions = ["ses:SendEmail"]
    resources = ["arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.from_email}"]
  }
  statement {
    sid     = "SSMParameters"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "kms:Decrypt"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.stack_name}/*",
      data.aws_kms_key.ssm.arn,
    ]
  }
}

resource "aws_iam_role_policy" "confirm_task" {
  name   = "${var.stack_name}-confirm-task"
  role   = aws_iam_role.confirm_task.id
  policy = data.aws_iam_policy_document.confirm_task.json
}

# ---------------------------------------------------------------------------
# VerifyDelivery — DynamoDB(Get) + SNS + SSM/KMS
# ---------------------------------------------------------------------------

resource "aws_iam_role" "verify_delivery" {
  name               = "${var.stack_name}-verify-delivery"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "verify_delivery_basic" {
  role       = aws_iam_role.verify_delivery.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "verify_delivery" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.reminders.arn]
  }
  statement {
    sid     = "SNS"
    effect  = "Allow"
    actions = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
  statement {
    sid     = "SSMParameters"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "kms:Decrypt"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.stack_name}/*",
      data.aws_kms_key.ssm.arn,
    ]
  }
}

resource "aws_iam_role_policy" "verify_delivery" {
  name   = "${var.stack_name}-verify-delivery"
  role   = aws_iam_role.verify_delivery.id
  policy = data.aws_iam_policy_document.verify_delivery.json
}
