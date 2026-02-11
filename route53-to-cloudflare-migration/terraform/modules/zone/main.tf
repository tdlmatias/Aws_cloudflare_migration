resource  "cloudflare_zone" "zone" {
    account_id  = var.account_id  # you may need to pass this in
    zone        = var.zone_name
}

resource "cloudflare_record" "dns_records" {
    for_each = {
        for idx, record in var.records :
        "${record.name}-${record.type}" => record
    }
    
    zone_id  = cloudflare_zone.zone.id
    name     = each.value.name
    type     = each.value.type
    value    = each.value.content
    ttl      = each.value.ttl
    proxied  = false
}
