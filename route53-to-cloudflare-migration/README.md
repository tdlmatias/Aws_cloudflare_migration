# Route53 → Cloudflare DNS Migration Automation

> Fully automated, zero-downtime DNS migration framework from AWS
> Route53 to Cloudflare using Python + Terraform + CI/CD.

------------------------------------------------------------------------

## 📌 Overview

This project automates migration of DNS zones from **AWS Route53** to
**Cloudflare** with:

-   ✅ Zero downtime migration strategy\
-   ✅ Full automation (no manual record creation)\
-   ✅ Infrastructure-as-Code via Terraform\
-   ✅ Idempotent re-runs\
-   ✅ CI/CD integration (GitHub Actions)\
-   ✅ Auditability via logs and Terraform state\
-   ✅ Batch multi-domain support

Designed for DevOps teams managing multiple production domains.

------------------------------------------------------------------------

## 🏗 Architecture

Route53 (Source) │ │ 
boto3 extraction ▼ Intermediate JSON (data/) │ │
Terraform modules ▼ Cloudflare (Target)

------------------------------------------------------------------------

## 📂 Project Structure

```console
route53-to-cloudflare-migration/
├── extract/
│   └── export_route53_to_json.py
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── modules/
│   │   └── zone/
│   └── terraform.tfvars
├── data/
│   └── domains.json
├── scripts/
│   └── run_all.sh
├── logs/
│   └── migration.log
├── .github/
│   └── workflows/
│       └── migrate_dns.yml
└── README.md
```

------------------------------------------------------------------------

## 🔐 Prerequisites

### AWS Credentials

Required permissions: - route53:ListHostedZones -
route53:ListResourceRecordSets

Environment variables: AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
AWS_DEFAULT_REGION

------------------------------------------------------------------------

### Cloudflare API Token

Required permissions: - Zone: Read - Zone: Edit - DNS: Edit

Environment variable: CLOUDFLARE_API_TOKEN

------------------------------------------------------------------------

### Installed Tools

-   Python 3.10+
-   Terraform 1.14.0
-   pip
-   Git

------------------------------------------------------------------------

## 🚀 Usage

### Step 1 --- Extract Route53 Records

python3 extract/export_route53_to_json.py

Output: data/domains.json

------------------------------------------------------------------------

### Step 2 --- Run Terraform

cd terraform terraform init terraform plan terraform apply -auto-approve

------------------------------------------------------------------------

### Step 3 --- Update Nameservers

After validation:

1.  Go to your domain registrar.
2.  Replace Route53 nameservers with Cloudflare nameservers.
3.  Wait for propagation.

------------------------------------------------------------------------

## 🔄 Zero-Downtime Strategy

1.  Export all Route53 records.
2.  Deploy to Cloudflare.
3.  Validate DNS resolution.
4.  Update registrar nameservers.
5.  Keep Route53 active for 48 hours as fallback.

------------------------------------------------------------------------

## ♻️ Idempotency

Terraform ensures:

-   Safe re-runs
-   No duplicate records
-   Diff-based updates
-   Full state tracking

------------------------------------------------------------------------

## 🔍 Observability

Logs: logs/migration.log

CI/CD logs available via GitHub Actions.

------------------------------------------------------------------------

## 🛠 CI/CD Integration

GitHub Actions workflow:

-   Manual trigger (workflow_dispatch)
-   Secure secrets management

Required secrets: AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
CLOUDFLARE_API_TOKEN

------------------------------------------------------------------------

## 🧩 Contributing

1.  Create feature branch
2.  Follow coding standards
3.  Ensure idempotency
4.  Submit PR with clear description

------------------------------------------------------------------------

## 🔐 Security Considerations

-   Never commit credentials
-   Use secret management
-   Limit API token scope
-   Enable MFA on AWS
-   Use remote Terraform backend in production

------------------------------------------------------------------------

## 🧱 Roadmap

-   Automated DNS validation
-   Drift detection
-   Proxy mode toggle support
-   Slack notifications
-   Rollback automation

------------------------------------------------------------------------

## ⚠️ Known Limitations

-   Advanced Route53 routing policies require custom mapping
-   Alias records require additional handling
-   DNSSEC must be re-enabled manually

------------------------------------------------------------------------

## 📄 License

MIT License (recommended)

------------------------------------------------------------------------

## 🤝 Maintainers

DevOps Architecture Team
