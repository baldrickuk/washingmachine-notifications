# Helper to create an EventBridge rule + target + Lambda permission in one block.
# Terraform doesn't support modules defined inline, so each rule is explicit —
# but the pattern is identical for every one.

# ---------------------------------------------------------------------------
# Sunday 09:00 UK — two rules to cover GMT and BST
# Lambda checks actual London time and exits early if wrong hour (DST guard).
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "sunday_email_bst" {
  name                = "${var.stack_name}-sunday-email-bst"
  description         = "Sunday 09:00 BST (08:00 UTC)"
  schedule_expression = "cron(0 8 ? * SUN *)"
}

resource "aws_cloudwatch_event_target" "sunday_email_bst" {
  rule = aws_cloudwatch_event_rule.sunday_email_bst.name
  arn  = aws_lambda_function.send_weekly_email.arn
}

resource "aws_lambda_permission" "sunday_email_bst" {
  statement_id  = "AllowEventBridgeSundayBST"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_weekly_email.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sunday_email_bst.arn
}

resource "aws_cloudwatch_event_rule" "sunday_email_gmt" {
  name                = "${var.stack_name}-sunday-email-gmt"
  description         = "Sunday 09:00 GMT (09:00 UTC)"
  schedule_expression = "cron(0 9 ? * SUN *)"
}

resource "aws_cloudwatch_event_target" "sunday_email_gmt" {
  rule = aws_cloudwatch_event_rule.sunday_email_gmt.name
  arn  = aws_lambda_function.send_weekly_email.arn
}

resource "aws_lambda_permission" "sunday_email_gmt" {
  statement_id  = "AllowEventBridgeSundayGMT"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_weekly_email.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sunday_email_gmt.arn
}

# ---------------------------------------------------------------------------
# Daily 08:00 UK — two rules for GMT and BST
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "daily_sms_bst" {
  name                = "${var.stack_name}-daily-sms-bst"
  description         = "Daily 08:00 BST (07:00 UTC)"
  schedule_expression = "cron(0 7 ? * * *)"
}

resource "aws_cloudwatch_event_target" "daily_sms_bst" {
  rule = aws_cloudwatch_event_rule.daily_sms_bst.name
  arn  = aws_lambda_function.send_daily_sms.arn
}

resource "aws_lambda_permission" "daily_sms_bst" {
  statement_id  = "AllowEventBridgeDailyBST"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_daily_sms.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_sms_bst.arn
}

resource "aws_cloudwatch_event_rule" "daily_sms_gmt" {
  name                = "${var.stack_name}-daily-sms-gmt"
  description         = "Daily 08:00 GMT (08:00 UTC)"
  schedule_expression = "cron(0 8 ? * * *)"
}

resource "aws_cloudwatch_event_target" "daily_sms_gmt" {
  rule = aws_cloudwatch_event_rule.daily_sms_gmt.name
  arn  = aws_lambda_function.send_daily_sms.arn
}

resource "aws_lambda_permission" "daily_sms_gmt" {
  statement_id  = "AllowEventBridgeDailyGMT"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_daily_sms.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_sms_gmt.arn
}

# ---------------------------------------------------------------------------
# Test SMS — every 10 minutes, disabled by default
# Enable manually in the AWS Console for testing escalation.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "test_sms" {
  name                = "${var.stack_name}-test-sms"
  description         = "TEST ONLY — disabled by default; enable via console to test escalating reminders"
  schedule_expression = "rate(10 minutes)"
  state               = "DISABLED"
}

resource "aws_cloudwatch_event_target" "test_sms" {
  rule  = aws_cloudwatch_event_rule.test_sms.name
  arn   = aws_lambda_function.send_daily_sms.arn
  input = jsonencode({ test = true })
}

resource "aws_lambda_permission" "test_sms" {
  statement_id  = "AllowEventBridgeTestSMS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.send_daily_sms.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.test_sms.arn
}

# ---------------------------------------------------------------------------
# Monday 09:01 UK — post-deploy verification (REL-3)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "verify_monday_bst" {
  name                = "${var.stack_name}-verify-monday-bst"
  description         = "Monday 09:01 BST (08:01 UTC) — verify Sunday reminder was sent"
  schedule_expression = "cron(1 8 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "verify_monday_bst" {
  rule = aws_cloudwatch_event_rule.verify_monday_bst.name
  arn  = aws_lambda_function.verify_delivery.arn
}

resource "aws_lambda_permission" "verify_monday_bst" {
  statement_id  = "AllowEventBridgeVerifyBST"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.verify_delivery.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.verify_monday_bst.arn
}

resource "aws_cloudwatch_event_rule" "verify_monday_gmt" {
  name                = "${var.stack_name}-verify-monday-gmt"
  description         = "Monday 09:01 GMT (09:01 UTC) — verify Sunday reminder was sent"
  schedule_expression = "cron(1 9 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "verify_monday_gmt" {
  rule = aws_cloudwatch_event_rule.verify_monday_gmt.name
  arn  = aws_lambda_function.verify_delivery.arn
}

resource "aws_lambda_permission" "verify_monday_gmt" {
  statement_id  = "AllowEventBridgeVerifyGMT"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.verify_delivery.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.verify_monday_gmt.arn
}
