terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  domains = jsondecode(file("${path.module}/../data/domains.json"))
}

module "zones" {
  for_each = local.domains

  source = "./modules/zones"

  zone_name = each.key
  records   = each.value.records
}