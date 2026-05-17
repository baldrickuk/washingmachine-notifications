locals {
  lambda_zip = "${path.module}/.lambda.zip"

  # Shared environment variables injected into every Lambda function
  lambda_env = {
    TABLE_NAME                   = aws_dynamodb_table.reminders.name
    FROM_EMAIL                   = var.from_email
    ANIMAL_TYPE                  = var.animal_type
    TWILIO_ACCOUNT_SID           = var.twilio_account_sid
    TWILIO_FROM_NUMBER           = var.twilio_from_number
    TWILIO_ENABLED               = var.twilio_enabled
    WHATSAPP_PHONE_NUMBER_ID     = var.whatsapp_phone_number_id
    WHATSAPP_REMINDER_TEMPLATE   = var.whatsapp_reminder_template
    WHATSAPP_ESCALATION_TEMPLATE = var.whatsapp_escalation_template
    WHATSAPP_CONGRATS_TEMPLATE   = var.whatsapp_congrats_template
    PARAM_TWILIO_AUTH_TOKEN      = aws_ssm_parameter.twilio_auth_token.name
    PARAM_WHATSAPP_ACCESS_TOKEN  = aws_ssm_parameter.whatsapp_access_token.name
    PARAM_WIFE_EMAIL             = aws_ssm_parameter.wife_email.name
    PARAM_WIFE_PHONE             = aws_ssm_parameter.wife_phone.name
    ALERT_TOPIC_ARN              = aws_sns_topic.alerts.arn
  }

  common_tags = {
    Project     = var.stack_name
    Environment = "production"
    ManagedBy   = "opentofu"
  }
}
