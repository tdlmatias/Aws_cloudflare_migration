terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 3.0.0"
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  zones = jsondecode(file("${path.module}/data/zones.json")).zones
  records = flatten([
    for zone in local.zones : [
      for record in zone.records : merge(record, { zone_name = zone.name })
    ]
  ])
}

resource "cloudflare_zone" "zones" {
  for_each = { for zone in local.zones : zone.name => zone }

  account_id = var.cloudflare_account_id
  zone       = each.value.name
  plan       = var.cloudflare_plan
}

resource "cloudflare_record" "records" {
  for_each = {
    for record in local.records :
    "${record.zone_name}-${record.name}-${record.type}-${record.value}-${lookup(record, "priority", "")}" => record
  }

  zone_id  = cloudflare_zone.zones[each.value.zone_name].id
  name     = each.value.name
  type     = each.value.type
  value    = each.value.value
  ttl      = each.value.ttl
  priority = lookup(each.value, "priority", null)
  proxied  = lookup(each.value, "proxied", false)
}
