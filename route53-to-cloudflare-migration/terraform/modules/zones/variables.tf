variable "account_id" {
  description = "Cloudflare account ID used to create the zone"
  type        = string
}

variable "zone_name" {
  description = "The domain name for the Cloudflare zone"
  type        = string
}

variable "records" {
  description = "DNS records for the zone"
  type = list(object({
    type    = string
    name    = string
    content = any
    ttl     = number
  }))
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token (optional if CLOUDFLARE_API_TOKEN env var is set)."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}