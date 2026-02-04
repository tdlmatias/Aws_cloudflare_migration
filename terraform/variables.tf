variable "cloudflare_api_token" {
  type        = string
  description = "Cloudflare API token with permissions to manage zones and DNS records."
  sensitive   = true
}

variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID where zones should be created."
}

variable "cloudflare_plan" {
  type        = string
  description = "Cloudflare plan for new zones."
  default     = "free"
}

variable "aws_region" {
  type        = string
  description = "AWS region used for authentication."
  default     = "us-east-1"
}

variable "aws_access_key" {
  type        = string
  description = "AWS access key ID used by the AWS provider."
  sensitive   = true
}

variable "aws_secret_key" {
  type        = string
  description = "AWS secret access key used by the AWS provider."
  sensitive   = true
}
