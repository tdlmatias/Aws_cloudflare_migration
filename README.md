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
cd terraform
terraform init
terraform apply -auto-approve \
  -var="cloudflare_api_token=${CLOUDFLARE_API_TOKEN}" \
  -var="cloudflare_account_id=${CLOUDFLARE_ACCOUNT_ID}" \
  -var="aws_access_key=${AWS_ACCESS_KEY_ID}" \
  -var="aws_secret_key=${AWS_SECRET_ACCESS_KEY}" \
  -var="aws_region=${AWS_REGION}"
```

## Notes
- `alias-records.json` should be reviewed and translated to the Cloudflare equivalent (often CNAME
  or provider-specific configuration).
- If a record name equals the zone apex, it is normalized to `@` in Cloudflare.
