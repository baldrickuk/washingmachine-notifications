output "confirm_url" {
  description = "Public confirmation endpoint (CloudFront — GB only)"
  value       = "https://${aws_cloudfront_distribution.confirm.domain_name}"
}

output "confirm_api_url" {
  description = "API Gateway origin URL — protected by X-Origin-Verify shared secret; direct requests without the header are rejected 403"
  value       = "https://${aws_apigatewayv2_api.confirm.id}.execute-api.${var.aws_region}.amazonaws.com"
}

output "reminders_table_name" {
  description = "DynamoDB reminders table name"
  value       = aws_dynamodb_table.reminders.name
}

output "dlq_url" {
  description = "Dead letter queue URL"
  value       = aws_sqs_queue.dlq.url
}

output "alert_topic_arn" {
  description = "SNS alert topic ARN"
  value       = aws_sns_topic.alerts.arn
}
