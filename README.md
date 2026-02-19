# Aws_cloudflare_migration

Migration of 12 Domain and DNS Records from Amazon AWS Route53 into Cloudflare.

## Overview
This repo provides a repeatable, low-touch workflow to export Route53 hosted zones with the AWS CLI
and apply them into Cloudflare using Terraform. The process produces a `zones.json` file that
Terraform consumes to create zones and DNS records. Alias records are collected separately for
manual review because Route53 aliases do not map 1:1 to Cloudflare.

## Prerequisites
- AWS CLI authenticated to the AWS account hosting the Route53 zones.
- `jq` and `python3`.
- Terraform 1.14.0 (aligned with CI and local validation workflows).
- Cloudflare API token with Zone and DNS edit permissions.

## Project Estructure
From project folder and files

```.
├── LICENSE
├── README.md
├── route53-to-cloudflare-migration
│   ├── README.md
│   ├── data
│   │   └── domain.json
│   ├── extract
│   │   └── export_route53_to_json.py
│   ├── logs
│   │   └── migration.log
│   ├── scripts
│   │   └── run_all.sh
│   └── terraform
│       ├── main.tf
│       ├── modules
│       │   └── zones
│       │       ├── main.tf
│       │       ├── output.tf
│       │       ├── variables.tf
│       │       └── version.tf
│       ├── terraform.tfvars
│       └── variables.tf
├── scripts
│   ├── export_route53.sh
│   └── route53_to_cloudflare.py
└── terraform
    ├── data
    │   └── zones.json
    ├── main.tf
    ├── terraform.tfvars
    └── variables.tf
```

## Export Route53 data
From the repo root:

```bash
./scripts/export_route53.sh terraform/data
```

This writes:
- `terraform/data/zones.json` (used by Terraform)
- `terraform/data/alias-records.json` (manual review)

## Terraform apply
From the repo root:

```bash
# Export AWS credentials via environment variables (used by AWS credential chain)
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"

# Export Cloudflare credentials
export CLOUDFLARE_API_TOKEN="your-cloudflare-token"
export CLOUDFLARE_ACCOUNT_ID="your-account-id"

cd terraform
terraform init
terraform apply -auto-approve \
  -var="cloudflare_api_token=${CLOUDFLARE_API_TOKEN}" \
  -var="cloudflare_account_id=${CLOUDFLARE_ACCOUNT_ID}" \
  -var="aws_region=${AWS_REGION}"
```

**Security Note:** Terraform now uses the standard AWS credential chain instead of passing credentials through variables. This prevents credential exposure in state files and logs. Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as environment variables, or use AWS instance profiles/OIDC for better security.

## Notes
- `alias-records.json` should be reviewed and translated to the Cloudflare equivalent (often CNAME
  or provider-specific configuration).
- If a record name equals the zone apex, it is normalized to `@` in Cloudflare.
