"""Route53 to Cloudflare migration tooling.

This package converts AWS Route53 hosted-zone exports into the deterministic
``zones.json`` document consumed by the Terraform configuration, and produces a
structured manual-review report for records that cannot be migrated
automatically (aliases, routing policies, and record types that do not map
1:1 to Cloudflare).
"""

from migration.converter import (
    SCHEMA_VERSION,
    ConversionResult,
    convert_hosted_zones,
)

__all__ = ["SCHEMA_VERSION", "ConversionResult", "convert_hosted_zones"]
