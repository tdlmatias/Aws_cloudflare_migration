terraform {
  required_version = ">= 1.6.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}


provider "cloudflare" {
  # api_token will be read from CLOUDFLARE_API_TOKEN environment variable
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
}

resource "cloudflare_dns_record" "records" {
  for_each = {
    for record in local.records :
    "${record.zone_name}-${record.name}-${record.type}-${record.value}-${lookup(record, "priority", "")}" => record
  }

  zone_id  = cloudflare_zone.zones[each.value.zone_name].id
  name     = each.value.name
  type     = each.value.type
  content  = each.value.value
  ttl      = each.value.ttl
  priority = lookup(each.value, "priority", null)
  proxied  = lookup(each.value, "proxied", false)
}
