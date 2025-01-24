resource "aws_iam_role" "firehose_role" {
  name_prefix = "firehose-delivery-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "firehose_s3_policy" {
  name_prefix = "firehose-s3-policy-${terraform.workspace}"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.firehose-destination.arn,
          "${aws_s3_bucket.firehose-destination.arn}/*"
        ]
      }
    ]
  })
}

# Expanded Firehose IAM role to allow more actions
resource "aws_iam_role_policy" "firehose_extended_policy" {
  name_prefix = "firehose-extended-policy-${terraform.workspace}"
  role = aws_iam_role.firehose_role.id

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

resource "aws_s3_bucket" "firehose-destination" {
  bucket = "${var.api_name}-${terraform.workspace}"

  force_destroy = true
}

resource "aws_kinesis_firehose_delivery_stream" "firehose" {
  name        = "${var.api_name}-${terraform.workspace}"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn           = aws_iam_role.firehose_role.arn
    bucket_arn         = aws_s3_bucket.firehose-destination.arn
    buffering_interval = 60
    prefix = "raw/"

    processing_configuration {
      enabled = true
      processors {
        type = "AppendDelimiterToRecord"
      }
    }
  }
}

