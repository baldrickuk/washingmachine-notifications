# Build the Lambda deployment package.
# Run terraform/build.sh before tofu plan/apply — it pip-installs
# dependencies and zips everything into terraform/.lambda.zip.
resource "null_resource" "lambda_build" {
  triggers = {
    source_hash       = filemd5("${path.module}/../src/handlers/app.py")
    requirements_hash = filemd5("${path.module}/../src/handlers/requirements.txt")
  }

  provisioner "local-exec" {
    command     = "${path.module}/build.sh"
    interpreter = ["bash"]
  }
}

locals {
  # Recomputed each plan so Lambda is redeployed whenever source changes
  lambda_source_hash = null_resource.lambda_build.triggers["source_hash"]
}

# ---------------------------------------------------------------------------
# Shared Lambda settings
# ---------------------------------------------------------------------------

locals {
  lambda_defaults = {
    filename      = local.lambda_zip
    runtime       = "python3.12"
    architectures = ["arm64"]
    memory_size   = 256
    timeout       = 30
  }
}

# ---------------------------------------------------------------------------
# SendWeeklyEmail
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "send_weekly_email" {
  function_name    = "${var.stack_name}-send-weekly-email"
  role             = aws_iam_role.send_weekly_email.arn
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_source_hash
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  memory_size      = local.lambda_defaults.memory_size
  timeout          = 30 # Calls SES + SSM + optional Pushover
  handler          = "app.send_weekly_email"

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = merge(local.lambda_env, {
      API_BASE_URL = "https://${aws_cloudfront_distribution.confirm.domain_name}"
    })
  }

  depends_on = [null_resource.lambda_build]
}

# ---------------------------------------------------------------------------
# SendDailySMS
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "send_daily_sms" {
  function_name    = "${var.stack_name}-send-daily-sms"
  role             = aws_iam_role.send_daily_sms.arn
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_source_hash
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  memory_size      = local.lambda_defaults.memory_size
  timeout          = 15 # DynamoDB read + optional Pushover call
  handler          = "app.send_daily_sms"

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = local.lambda_env
  }

  depends_on = [null_resource.lambda_build]
}

# ---------------------------------------------------------------------------
# ConfirmTask
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "confirm_task" {
  function_name                  = "${var.stack_name}-confirm-task"
  role                           = aws_iam_role.confirm_task.arn
  filename                       = local.lambda_defaults.filename
  source_code_hash               = local.lambda_source_hash
  runtime                        = local.lambda_defaults.runtime
  architectures                  = local.lambda_defaults.architectures
  memory_size                    = local.lambda_defaults.memory_size
  reserved_concurrent_executions = 5
  timeout                        = 10 # Synchronous API call — tighter timeout
  handler                        = "app.confirm_task"

  environment {
    variables = local.lambda_env
  }

  depends_on = [null_resource.lambda_build]
}

# ---------------------------------------------------------------------------
# VerifyDelivery
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "verify_delivery" {
  function_name    = "${var.stack_name}-verify-delivery"
  role             = aws_iam_role.verify_delivery.arn
  filename         = local.lambda_defaults.filename
  source_code_hash = local.lambda_source_hash
  runtime          = local.lambda_defaults.runtime
  architectures    = local.lambda_defaults.architectures
  memory_size      = local.lambda_defaults.memory_size
  timeout          = 15 # DynamoDB read + optional SNS publish
  handler          = "app.verify_delivery"

  environment {
    variables = local.lambda_env
  }

  depends_on = [null_resource.lambda_build]
}
