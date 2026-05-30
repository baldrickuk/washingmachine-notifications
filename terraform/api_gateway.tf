resource "aws_apigatewayv2_api" "confirm" {
  name                         = "${var.stack_name}-confirm-api"
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = true
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.stack_name}"
  retention_in_days = 30
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.confirm.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId    = "$context.requestId"
      ip           = "$context.identity.sourceIp"
      requestTime  = "$context.requestTime"
      httpMethod   = "$context.httpMethod"
      routeKey     = "$context.routeKey"
      status       = "$context.status"
      errorMessage = "$context.error.message"
    })
  }
}

resource "aws_apigatewayv2_integration" "confirm_task" {
  api_id                 = aws_apigatewayv2_api.confirm.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.confirm_task.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "confirm" {
  api_id    = aws_apigatewayv2_api.confirm.id
  route_key = "GET /confirm"
  target    = "integrations/${aws_apigatewayv2_integration.confirm_task.id}"
}

resource "aws_lambda_permission" "api_gateway_confirm" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.confirm_task.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.confirm.execution_arn}/*/*/confirm"
}
