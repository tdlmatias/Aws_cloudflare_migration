variable "cloudflare_api_token" {
  type        = string
  description = "Cloudflare API token with Zone:Edit and DNS:Edit permissions. Prefer the CLOUDFLARE_API_TOKEN environment variable over a .tfvars file."
  sensitive   = true
}

variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID (32 hex characters) where zones are created."

  validation {
    condition     = can(regex("^[0-9a-f]{32}$", var.cloudflare_account_id))
    error_message = "cloudflare_account_id must be a 32-character hexadecimal string."
  }
}

variable "zones_file" {
  type        = string
  description = "Override path to the zones.json document (used by terraform test fixtures). Defaults to data/zones.json."
  default     = null
  nullable    = true
}
