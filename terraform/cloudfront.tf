resource "aws_cloudfront_distribution" "confirm" {
  enabled     = true
  comment     = "${var.stack_name} — GB-only confirmation endpoint"
  price_class = "PriceClass_100"

  origin {
    origin_id   = "ApiGatewayOrigin"
    domain_name = "${aws_apigatewayv2_api.confirm.id}.execute-api.${var.aws_region}.amazonaws.com"

    custom_header {
      name  = "X-Origin-Verify"
      value = var.origin_verify_token
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id = "ApiGatewayOrigin"
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]

    # CachingDisabled — confirmation links must always hit the origin
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # AllViewerExceptHostHeader — forwards query strings; Host excluded so API GW gets its own hostname
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"

    viewer_protocol_policy = "redirect-to-https"
  }

  restrictions {
    geo_restriction {
      restriction_type = "whitelist"
      locations        = ["GB"]
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
