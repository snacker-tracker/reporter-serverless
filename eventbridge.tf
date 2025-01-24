resource "aws_cloudwatch_event_bus" "everything" {
  name = "${var.api_name}-${terraform.workspace}"
}

resource "aws_cloudwatch_event_rule" "everything" {
  name        = "${var.api_name}-capture-everything-${terraform.workspace}"
  description = "I really want everything"
  event_bus_name = aws_cloudwatch_event_bus.everything.name

  event_pattern = jsonencode({
    "account": [data.aws_caller_identity.current.account_id]
  })
}

resource "aws_cloudwatch_event_target" "firehose" {
  event_bus_name = aws_cloudwatch_event_bus.everything.name
  rule      = aws_cloudwatch_event_rule.everything.name
  #target_id = "ToFirehose"
  arn       = aws_kinesis_firehose_delivery_stream.firehose.arn
  role_arn = aws_iam_role.eventbridge_delivery_role.arn

  dead_letter_config {
    arn = "arn:aws:sqs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:SQS_QUEUE_NAME"
  }
}

resource "aws_iam_role" "eventbridge_delivery_role" {
  name_prefix = "${var.api_name}-eb-delivery-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_delivery_role_policy" {
  name_prefix = "${var.api_name}-eventbridge-delivery-role-policy-${terraform.workspace}"
  role = aws_iam_role.eventbridge_delivery_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
            "firehose:PutRecord",
        ]
        Resource = [aws_kinesis_firehose_delivery_stream.firehose.arn]
      }
    ]
  })
}

# Expanded Firehose IAM role to allow more actions
resource "aws_iam_role_policy" "eventbridge_delivery_role_extended_policy" {
  name_prefix = "${var.api_name}-firehose-extended-policy-${terraform.workspace}"
  role = aws_iam_role.eventbridge_delivery_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:CreateLogStream"
        ]
        Resource = ["*"]
      }
    ]
  })
}

