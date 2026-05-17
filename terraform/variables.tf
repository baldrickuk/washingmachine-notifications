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

variable "twilio_enabled" {
  description = "Set to 'true' to enable Twilio SMS"
  type        = string
  default     = "false"
}

variable "twilio_account_sid" {
  description = "Twilio Account SID (optional)"
  type        = string
  default     = "unused"
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token (optional, stored in Secrets Manager)"
  type        = string
  sensitive   = true
  default     = "unused"
}

variable "twilio_from_number" {
  description = "Twilio phone number in E.164 format (optional)"
  type        = string
  default     = "unused"
}

variable "twilio_whatsapp_enabled" {
  description = "Set to 'true' to send WhatsApp messages via Twilio (reuses Twilio credentials)"
  type        = string
  default     = "false"
}

variable "twilio_whatsapp_from" {
  description = "Twilio WhatsApp-enabled sender number, e.g. whatsapp:+14155238886"
  type        = string
  default     = ""
}

variable "whatsapp_phone_number_id" {
  description = "Meta WhatsApp Business phone number ID (optional)"
  type        = string
  default     = ""
}

variable "whatsapp_access_token" {
  description = "Meta WhatsApp access token (optional, stored in Secrets Manager)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "whatsapp_reminder_template" {
  description = "Approved Meta template name for the initial Sunday reminder"
  type        = string
  default     = "filter_reminder"
}

variable "whatsapp_escalation_template" {
  description = "Approved Meta template name for daily escalation reminders"
  type        = string
  default     = "filter_escalation"
}

variable "whatsapp_congrats_template" {
  description = "Approved Meta template name for the congratulations message"
  type        = string
  default     = "filter_confirmed"
}
