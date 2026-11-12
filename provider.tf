provider "aws" {
  region = "ap-southeast-1"

  default_tags {
    tags = {
      Repository  = "git@github.com:snacker-tracker/reporter-serverless.git"
      Project     = "snacker-tracker"
      Component   = "reporter-serverless"
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
      Version     = var.version_label
    }
  }
}

terraform {
  backend "s3" {
    bucket               = "lmacguire-terraform"
    key                  = "terraform.tfstate"
    workspace_key_prefix = "member-accounts/snacker-tracker/reporter-serverless"
    region               = "ap-southeast-1"
    use_lockfile         = true
  }
}


provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"

  default_tags {
    tags = {
      Repository  = "git@github.com:snacker-tracker/reporter-serverless.git"
      Project     = "snacker-tracker"
      Component   = "reporter-serverless"
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
      Version     = var.version_label
    }
  }
}
