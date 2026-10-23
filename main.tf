data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

# Required on every IAM role this configuration creates. Managed in
# snacker-tracker/aws-infra (runtime_role_boundary.tf): it denies all IAM,
# and the deploy role may only create or change roles that carry it.
locals {
  runtime_role_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/runtime-role-permissions-boundary"
}
