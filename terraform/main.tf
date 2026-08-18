terraform {
  required_version = "~> 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5"
    }
  }
}

# This configuration only creates Cloudflare resources. AWS is used exclusively
# by the read-only export step (scripts/export_route53.sh), so no AWS provider
# or AWS credentials are required here.
#
# The API token is supplied via the CLOUDFLARE_API_TOKEN environment variable,
# which the provider reads natively. It is deliberately NOT a Terraform variable:
# variable values are recorded inside a saved plan (`terraform plan -out`), so
# sourcing the token from a variable would bake it into the plan file and let a
# saved plan pin the planning credential at apply time. Reading it from the
# environment keeps the token out of the plan and state, and lets a two-phase
# plan/apply pipeline authenticate each phase with its own token.
provider "cloudflare" {}

locals {
  data_file = coalesce(var.zones_file, "${path.module}/data/zones.json")
  zones     = jsondecode(file(local.data_file)).zones

  records = flatten([
    for zone in local.zones : [
      for record in zone.records : merge(record, { zone_name = zone.name })
    ]
  ])

  # Deterministic, collision-detecting map key for DNS records. priority is
  # nullable (present-but-null for non-MX records), so it is normalised to an
  # empty string before joining rather than passed to join() as null.
  record_map = {
    for record in local.records :
    join("|", [
      record.zone_name,
      record.name,
      record.type,
      tostring(record.content),
      lookup(record, "priority", null) == null ? "" : tostring(record.priority),
    ]) => record
  }
}

# Guard against a destructive apply triggered by an empty or incomplete export.
# If zones.json has no zones, the plan would delete every managed zone.
resource "terraform_data" "guard" {
  input = length(local.zones)

  lifecycle {
    precondition {
      condition     = length(local.zones) > 0
      error_message = "data/zones.json contains no zones. Refusing to apply to avoid destroying existing Cloudflare zones. Re-run the export before applying."
    }
  }
}

resource "cloudflare_zone" "zones" {
  for_each = { for zone in local.zones : zone.name => zone }

  account = {
    id = var.cloudflare_account_id
  }
  name = each.value.name
}

resource "cloudflare_dns_record" "records" {
  for_each = local.record_map

  zone_id  = cloudflare_zone.zones[each.value.zone_name].id
  name     = each.value.name
  type     = each.value.type
  content  = each.value.content
  ttl      = each.value.ttl
  priority = lookup(each.value, "priority", null)
  # Records are unproxied by default so DNS behaviour matches Route53 during
  # cutover; enable the Cloudflare proxy explicitly per record when desired.
  proxied = lookup(each.value, "proxied", false)
}
