data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

# Required on every IAM role this configuration creates. Managed in
# snacker-tracker/aws-infra (runtime_role_boundary_reporter_serverless.tf):
# it allows only this app's own bucket, stream, event bus, queues and log
# groups, and the deploy role may only create or change roles that carry it.
# A role needing anything else needs that boundary changed first.
locals {
  runtime_role_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/reporter-serverless-runtime-boundary"
}
