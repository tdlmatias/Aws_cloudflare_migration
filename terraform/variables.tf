variable "cloudflare_api_token" {
  type        = string
  description = "Cloudflare API token with permissions to manage zones and DNS records."
  sensitive   = true
  nullable    = true

  validation {
    condition = var.cloudflare_api_token == null || (
      length(var.cloudflare_api_token) == 40 &&
      can(regex("^[A-Za-z0-9_-]+$", var.cloudflare_api_token))
    )
    error_message = "cloudflare_api_token must be a 40-character API token using only letters, numbers, hyphens, and underscores."
  }
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
