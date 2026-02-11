variable "zone_name" {
    type        = string
}

variable "records" {
    type         = list(object({
        type     = string
        name     = string
        content  = any
        ttl      = number
    }))
}