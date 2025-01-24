variable "project_description" {
  description = "Short blurb about the project"
  type        = string
  default     = "API Gateway + EventBridge + Firehose + S3 integration for easy public webhooks"
}

variable "domain" {
  description = "hostname of the API"
  type = string
  default = "reporter.khanom.xyz"
}

variable "zone_id" {
  description = "zone ID under which domain sits"
  type = string
  default = "Z015639717HE01PZZ2H3K"
}

variable "api_name" {
  description = "A serverless snacker-tracker reporter"
  type = string
  default = "snacker-tracker"
}

variable "image_version" {
  description = "Version to use when tagging the docker image"
  type = string
  default = "latest"
}
