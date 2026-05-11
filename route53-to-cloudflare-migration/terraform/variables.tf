variable "cloudflare_api_token" {
  description = "Cloudflare API token (optional if CLOUDFLARE_API_TOKEN env var is set)."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID used when creating zones"
  type        = string
}
