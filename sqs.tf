resource "aws_sqs_queue" "s3_to_lambda" {
  name = "${var.api_name}-s3-to-lambda-${terraform.workspace}"

  # Must be >= Lambda timeout to prevent duplicate processing
  visibility_timeout_seconds = 360
}

resource "aws_sqs_queue_policy" "s3_to_lambda" {
  queue_url = aws_sqs_queue.s3_to_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "s3.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.s3_to_lambda.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.firehose-destination.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue" "eventbridge_dlq" {
  name = "${var.api_name}-eventbridge-dlq-${terraform.workspace}"
}
