# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the maintainers via a
GitHub Security Advisory ("Report a vulnerability" on the Security tab) rather
than a public issue. Include reproduction steps and impact. We aim to
acknowledge within 5 business days.

## Scope and handling

* **Never commit secrets.** AWS credentials, Cloudflare tokens, and Terraform
  state must not be committed. `*.tfvars` and generated data are git-ignored;
  `gitleaks` runs in CI and as a pre-commit hook.
* If you believe a credential was exposed, treat it as compromised: rotate it
  immediately (Cloudflare token, AWS role/keys) and notify the maintainers.
* Terraform state contains sensitive DNS data — store it in an encrypted,
  access-controlled remote backend.

See `docs/SECURITY_MODEL.md` for the full credential, OIDC, and CI/CD security
model.

## Supported configuration

This project targets Terraform `~> 1.9`, the Cloudflare provider `~> 5`, and
Python `>= 3.10`.
