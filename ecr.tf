resource "aws_ecr_repository" "append_to_bronze" {
  name         = "snacker-tracker-lambda/append-to-bronze"
  force_delete = true
}
