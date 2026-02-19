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
  domains_file = fileexists("${path.module}/../data/domains.json") ? "${path.module}/../data/domains.json" : "${path.module}/../data/domain.json"
  domains      = jsondecode(file(local.domains_file))
}

module "zones" {
  for_each = local.domains

  source = "./modules/zones"

  account_id = var.cloudflare_account_id
  zone_name  = each.key
  records    = each.value.records
}

