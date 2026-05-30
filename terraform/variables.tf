variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-2"
}

variable "stack_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "washingmachine-notifications"
}

variable "wife_email" {
  description = "Recipient email address (stored in Secrets Manager)"
  type        = string
  sensitive   = true
}

variable "wife_phone" {
  description = "Recipient mobile number in E.164 format (stored in Secrets Manager)"
  type        = string
  sensitive   = true
}

variable "from_email" {
  description = "Verified SES sender email address"
  type        = string
}

variable "alert_email" {
  description = "Email address for operational alerts (Lambda errors, DLQ, throttling)"
  type        = string
}

variable "animal_type" {
  description = "Animal photo reward on confirmation (bunny, cat, dog, fox)"
  type        = string
  default     = "bunny"
}

variable "test_sms_interval_seconds" {
  description = "Minimum seconds between test reminders (default 30)"
  type        = number
  default     = 30
}

variable "pushover_app_token" {
  description = "Pushover application token (stored in SSM SecureString)"
  type        = string
  sensitive   = true
}

variable "pushover_user_key" {
  description = "Pushover user key (stored in SSM SecureString)"
  type        = string
  sensitive   = true
}

variable "origin_verify_token" {
  description = "Shared secret injected by CloudFront as X-Origin-Verify header; blocks direct execute-api access"
  type        = string
  sensitive   = true
  default     = ""
}
