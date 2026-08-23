provider "aws" {
  region = "ap-southeast-1"

  default_tags {
    tags = {
      Repository = "git@github.com:snacker-tracker/reporter-serverless.git"
      Project = "snacker-tracker"
      Component = "reporter-serverless"
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
      Version = var.version_label
    }
  }
}

terraform {
  backend "s3" {
    bucket = "snacker-tracker-aws-infra-tfstate"
    key    = "snacker-tracker-reporter-serverless"
    region = "ap-southeast-1"
  }
}


provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"

  default_tags {
    tags = {
      Repository = "git@github.com:snacker-tracker/reporter-serverless.git"
      Project = "snacker-tracker"
      Component = "reporter-serverless"
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
      Version = var.version_label
    }
  }
}
