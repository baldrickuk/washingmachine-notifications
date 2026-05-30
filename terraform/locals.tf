locals {
  lambda_zip = "${path.module}/.lambda.zip"

  # Shared environment variables injected into every Lambda function
  lambda_env = {
    TABLE_NAME               = aws_dynamodb_table.reminders.name
    FROM_EMAIL               = var.from_email
    ANIMAL_TYPE              = var.animal_type
    PARAM_PUSHOVER_APP_TOKEN = aws_ssm_parameter.pushover_app_token.name
    PARAM_PUSHOVER_USER_KEY  = aws_ssm_parameter.pushover_user_key.name
    PARAM_WIFE_EMAIL         = aws_ssm_parameter.wife_email.name
    PARAM_WIFE_PHONE         = aws_ssm_parameter.wife_phone.name
    ALERT_TOPIC_ARN          = aws_sns_topic.alerts.arn
  }

  common_tags = {
    Project     = var.stack_name
    Environment = "production"
    ManagedBy   = "opentofu"
  }
}
