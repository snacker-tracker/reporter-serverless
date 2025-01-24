resource "aws_api_gateway_rest_api" "api" {
  name        = "${var.api_name}-${terraform.workspace}"
  description = var.project_description

  endpoint_configuration {
    types = ["EDGE"]
  }

  #put_rest_api_mode = "merge"

  body = "${data.template_file.codingtips_api_swagger.rendered}"
}

data "template_file" "codingtips_api_swagger" {
  template = "${file("./swagger.yml")}"

  vars = {
    aws_region = data.aws_region.current.region
    eventbus_name = aws_cloudwatch_event_bus.everything.name
    integration_role = aws_iam_role.api_gateway_firehose_role.arn
  }
}


resource "aws_iam_role" "api_gateway_firehose_role" {
  name = "${var.api_name}-api-gateway-firehose-role-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_gateway_firehose_policy" {
  name_prefix = "${var.api_name}-api-gateway-firehose-policy-${terraform.workspace}"
  role = aws_iam_role.api_gateway_firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = [
          aws_cloudwatch_event_bus.everything.arn
        ]
      }
    ]
  })
}


resource "aws_api_gateway_deployment" "deployment" {
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.api.body
    ]))
  }

  rest_api_id = aws_api_gateway_rest_api.api.id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "api-gateway" {
  name              = "API-Gateway-Execution-Logs_${aws_api_gateway_rest_api.api.id}/${terraform.workspace}"
  retention_in_days = 1
}

resource "aws_api_gateway_stage" "stage" {
  deployment_id = aws_api_gateway_deployment.deployment.id
  rest_api_id   = aws_api_gateway_rest_api.api.id
  stage_name    = terraform.workspace

  depends_on = [aws_cloudwatch_log_group.api-gateway]
}

resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name              = "/aws/apigateway/${aws_api_gateway_rest_api.api.name}/${terraform.workspace}"
  retention_in_days = 30
}

resource "aws_acm_certificate" "api_domain_cert" {
  provider = aws.us-east-1

  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_domain_name" "api_domain" {
  domain_name     = var.domain
  certificate_arn = aws_acm_certificate.api_domain_cert.arn

  endpoint_configuration {
    types = ["EDGE"]
  }
}

resource "aws_api_gateway_base_path_mapping" "api_domain_mapping" {
  api_id      = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.stage.stage_name
  domain_name = aws_api_gateway_domain_name.api_domain.domain_name
}

resource "aws_route53_record" "cert_validation" {
  provider = aws.us-east-1

  for_each = {
    for dvo in aws_acm_certificate.api_domain_cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = var.zone_id
}

resource "aws_route53_record" "api_domain" {
  zone_id = var.zone_id
  name    = var.domain
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.api_domain.cloudfront_domain_name
    zone_id                = aws_api_gateway_domain_name.api_domain.cloudfront_zone_id
    evaluate_target_health = true
  }
}

resource "aws_acm_certificate_validation" "cert_validation" {
  provider = aws.us-east-1

  certificate_arn         = aws_acm_certificate.api_domain_cert.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}



resource "aws_api_gateway_usage_plan" "event_api" {
  name         = "${var.api_name}-${terraform.workspace}"
  description  = "my description"
  product_code = "${var.api_name}-${terraform.workspace}"

  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.stage.stage_name
  }

  quota_settings {
    limit  = 1000
    offset = 2
    period = "WEEK"
  }

  throttle_settings {
    burst_limit = 5
    rate_limit  = 10
  }
}

resource "aws_api_gateway_api_key" "bangkok-office" {
  name = "bangkok-office"
}

resource "aws_api_gateway_usage_plan_key" "bangkok-office" {
  key_id        = aws_api_gateway_api_key.bangkok-office.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.event_api.id
}
