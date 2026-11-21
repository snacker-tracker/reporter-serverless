resource "aws_sqs_queue" "eventbridge_dlq" {
  name = "${var.api_name}-eventbridge-dlq-${terraform.workspace}"
}
