provider "aws" {
  region = "ap-southeast-1"

  default_tags {
    tags = {
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
      Version = var.version
    }
  }
}

terraform {
  backend "s3" {
    bucket = "lmacguire-terraform"
    key    = "snacker-tracker-reporter-serverless"
    region = "ap-southeast-1"
  }
}


provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"

  default_tags {
    tags = {
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
    }
  }
}
