# modules/zones/outputs.tf
output "zone_id" {
  value = cloudflare_zone.zone.id
}