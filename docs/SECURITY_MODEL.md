# Security Model

## Credentials

| Secret | Where it lives | Scope |
| ------ | -------------- | ----- |
| AWS access | GitHub OIDC → assumed IAM role (export only) | Read-only Route53 |
| Cloudflare API token | `TF_VAR_cloudflare_api_token` / env / GitHub Environment secret | `Zone:Edit`, `DNS:Edit` |
| Cloudflare account id | env / secret | Non-secret identifier, still not committed |

Principles:

* **No long-lived AWS keys.** The export workflow uses GitHub OIDC
  (`permissions: id-token: write`) to assume a read-only role.
* **Terraform never receives AWS credentials** — it only manages Cloudflare.
* Secrets are passed via environment (`TF_VAR_*`), never written to `.tfvars`
  files or committed. `terraform.tfvars` is git-ignored; only
  `terraform.tfvars.example` (placeholders) is tracked.
* The Cloudflare token variable is `sensitive` so it is redacted from plan output.

## Recommended AWS OIDC trust policy (export role)

Replace `<ACCOUNT_ID>` with the AWS account that now holds the hosted zones.
Keep the repository name in the `sub` condition **exactly as GitHub spells it**
(`tdlmatias/Aws_cloudflare_migration`, capital `A`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike": { "token.actions.githubusercontent.com:sub": "repo:tdlmatias/Aws_cloudflare_migration:*" }
    }
  }]
}
```

> **Case sensitivity matters.** GitHub's OIDC token carries the repository's
> canonical name in the `sub` claim (`repo:tdlmatias/Aws_cloudflare_migration:...`),
> and IAM `StringLike` conditions are case-sensitive. A trust policy written with
> a lower-cased repo name will reject the token and the export workflow fails at
> "Configure AWS credentials" with an unhelpful `Not authorized to perform
> sts:AssumeRoleWithWebIdentity` error. Tighten `:*` to a specific ref (e.g.
> `...:ref:refs/heads/main` or `...:environment:export`) once the role works.

## Minimal IAM permissions (export role)

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["route53:ListHostedZones", "route53:ListResourceRecordSets"],
    "Resource": "*"
  }]
}
```

## Cloudflare API token scope

Create a scoped token, not a global API key: **Zone → Zone → Edit** and
**Zone → DNS → Edit**, limited to the specific account/zones where possible.

## Terraform state

State contains the full DNS graph and is sensitive. Use an encrypted, locked,
access-controlled backend (`terraform/backend.tf.example`): S3 with
`encrypt = true` and `use_lockfile = true` (or a DynamoDB lock table on
Terraform < 1.10). Restrict who can read the state bucket.

## CI/CD hardening

* Every workflow declares least-privilege `permissions` (`contents: read` by
  default; `id-token: write` only for the OIDC export).
* Production apply is `workflow_dispatch` only, gated by a protected
  `production` GitHub Environment with required reviewers, a typed confirmation
  input, and a `concurrency` lock. No apply on push.
* Job timeouts and `concurrency` groups are set to bound runaway or racing runs.
* `security.yml` runs gitleaks (secret scanning) and checkov (IaC scanning) on
  PRs, pushes to `main`, and weekly.

## Supply chain

* GitHub Actions are pinned to release tags. For stronger guarantees, pin
  third-party actions (e.g. `gitleaks/gitleaks-action`) to a **commit SHA**.
* Dependabot (`.github/dependabot.yml`) updates pip, GitHub Actions, and
  Terraform providers weekly.
* `pre-commit` includes `detect-private-key` and `gitleaks`.

## Data handling

* Generated `hosted-zones.json`, `records-*.json`, and `manual-review.json` are
  git-ignored. Only the reviewed `zones.json` is committed.
* Private hosted zones are never migrated into public Cloudflare zones.
