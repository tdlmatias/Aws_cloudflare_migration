variable "zone_name" {
    description = "The domain name for the Cloudflare zone"
    type        = string
}

variable "records" {
    description = "DNS records for the zone"
    type         = list(object({
        type     = string
        name     = string
        content  = any
        ttl      = number
    }))
}