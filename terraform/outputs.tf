output "zone_ids" {
  description = "Map of zone name to the created Cloudflare zone id."
  value       = { for name, zone in cloudflare_zone.zones : name => zone.id }
}

output "zone_count" {
  description = "Number of Cloudflare zones managed by this configuration."
  value       = length(cloudflare_zone.zones)
}

output "record_count" {
  description = "Number of Cloudflare DNS records managed by this configuration."
  value       = length(cloudflare_dns_record.records)
}
