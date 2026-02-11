terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  domains = jsondecode(file("${path.module}/../data/domain.json"))
}

module "zones" {
  for_each = local.domains

  source = "./modules/zone"

  account_id = var.cloudflare_account_id
  zone_name  = each.key
  records    = each.value.records
}
