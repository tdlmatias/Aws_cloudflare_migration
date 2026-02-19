terraform {
  required_version = ">= 1.14.0"

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
  # Uses AWS credential chain (environment variables, instance profiles, etc.)
  # Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables
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

  account = {
    id = var.cloudflare_account_id
  }
  name = each.value.name
}

resource "cloudflare_dns_record" "records" {
  for_each = {
    for record in local.records :
    "${record.zone_name}-${record.name}-${record.type}-${record.content}-${lookup(record, "priority", "")}" => record
  }

  zone_id  = cloudflare_zone.zones[each.value.zone_name].id
  name     = each.value.name
  type     = each.value.type
  content  = each.value.content
  ttl      = each.value.ttl
  priority = lookup(each.value, "priority", null)
  proxied  = lookup(each.value, "proxied", false)
}
