resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.api_name}-lambda-execution-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action    = "sts:AssumeRole"
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_logs" {
  name_prefix = "${var.api_name}-lambda-logs-${terraform.workspace}"
  role        = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = ["arn:aws:logs:*:*:*"]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_s3" {
  name_prefix = "${var.api_name}-lambda-s3-${terraform.workspace}"
  role        = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.firehose-destination.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.firehose-destination.arn}/raw/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = ["${aws_s3_bucket.firehose-destination.arn}/bronze/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_sqs" {
  name_prefix = "${var.api_name}-lambda-sqs-${terraform.workspace}"
  role        = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [aws_sqs_queue.s3_to_lambda.arn]
      }
    ]
  })
}

resource "aws_lambda_function" "append_to_bronze" {
  function_name = "${var.api_name}-append-to-bronze-${terraform.workspace}"
  role          = aws_iam_role.lambda_execution_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.append_to_bronze.repository_url}:${var.version_label}-append"
  timeout       = 300
  memory_size   = 1024

  environment {
    variables = {
      BRONZE_BUCKET = aws_s3_bucket.firehose-destination.bucket
    }
  }
}

resource "aws_lambda_function" "rebuild_bronze" {
  function_name = "${var.api_name}-rebuild-bronze-${terraform.workspace}"
  role          = aws_iam_role.lambda_execution_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.append_to_bronze.repository_url}:${var.version_label}-rebuild"
  timeout       = 900
  memory_size   = 1024

  environment {
    variables = {
      BRONZE_BUCKET = aws_s3_bucket.firehose-destination.bucket
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_to_append" {
  event_source_arn = aws_sqs_queue.s3_to_lambda.arn
  function_name    = aws_lambda_function.append_to_bronze.arn
  batch_size       = 1
}
