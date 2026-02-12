
resource "cloudflare_zone" "zone" {
  account = {
    id = var.account_id
  } # you may need to pass this in
  name = var.zone_name
}

locals {
  records_map = {
    for idx, record in var.records :
    "${idx}-${try(record.type, "UNK")}-${try(record.name, "noname")}" => record
  }
}

resource "cloudflare_dns_record" "dns_records" {
  for_each = local.records_map

  # ✅ correct: reference the resource, not a var.*
  zone_id = cloudflare_zone.zone.id

  name = each.value.name
  type = each.value.type

  # v5 uses `content` (not `value`)
  content = coalesce(
    try(each.value.content, null),
    try(each.value.value, null)
  )

  ttl     = try(each.value.ttl, 1)
  proxied = try(each.value.proxied, null)

  priority = try(each.value.priority, null)
  comment  = try(each.value.comment, null)
  tags     = try(each.value.tags, null)
}
