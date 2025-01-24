provider "aws" {
  region = "ap-southeast-2"
  
  default_tags {
    Environment = "Development"
    ManagedBy   = "Terraform"
  }
}
