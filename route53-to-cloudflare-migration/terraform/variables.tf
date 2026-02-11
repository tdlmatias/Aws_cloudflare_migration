variable "cloudflare_api_token" {
  description = "API token with permissions to manage zones and DNS records"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID used when creating zones"
  type        = string
}
