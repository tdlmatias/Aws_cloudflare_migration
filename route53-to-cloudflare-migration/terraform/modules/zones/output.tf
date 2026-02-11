# modules/zone/output.tf
output "zone_id" {
  value = cloudflare_zone.zone.id
}
