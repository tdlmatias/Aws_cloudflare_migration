terraform {
    required_providers {
        cloudflare  = {
            source  = "cloudflare/cloudflare"
            version = "~> 4.0"
        }
    }
}

provider "cloudflare" {
    api_token = var.cloudflare_api_token
}

locals {
    domains = jsondecode(file("${path.modules}/../data/domains.json"))
}

modules "zones" {
    for_each = local.domains

    source = "./modules/zones"

    zone_name = each.key
    records   = each.value.records
}