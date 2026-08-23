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
  default = "Z0781732PCOBWRVFR9YS"
}

variable "api_name" {
  description = "A serverless snacker-tracker reporter"
  type = string
  default = "snacker-tracker"
}

variable "version_label" {
  description = "Version to tag things with"
  type = string
  default = "latest"
}
