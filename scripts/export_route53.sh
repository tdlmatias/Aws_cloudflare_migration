#!/usr/bin/env bash
#
# Export every Route53 hosted zone to JSON and convert it into the
# Terraform-consumable zones.json plus a manual-review report.
#
# Usage:
#   scripts/export_route53.sh [OUTPUT_DIR]
#
# OUTPUT_DIR defaults to terraform/data. The AWS CLI must be authenticated with
# read-only Route53 permissions (route53:ListHostedZones,
# route53:ListResourceRecordSets). No infrastructure is modified.
#
# Requires: bash, coreutils (mktemp/date/mkdir/mv/rm/dirname), aws, jq, python3.
# The aws/jq/python3 tools are checked explicitly below.
#
set -euo pipefail

# Resolve the repository root from this script's location so the tool works
# regardless of the current working directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"

out_dir="${1:-terraform/data}"
# Make a relative output dir relative to the repo root, not the caller's cwd.
case "${out_dir}" in
  /*) : ;;
  *) out_dir="${REPO_ROOT}/${out_dir}" ;;
esac

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

# --- Dependency checks -------------------------------------------------------
for tool in aws jq python3; do
  command -v "${tool}" >/dev/null 2>&1 || die "required tool '${tool}' is not installed"
done

# --- Work in a temporary directory, publish atomically on success -----------
# Create the temp dir as a sibling of the output dir so the final publish is an
# atomic same-filesystem rename rather than a cross-device copy.
mkdir -p "$(dirname -- "${out_dir}")"
work_dir="$(mktemp -d "${out_dir}.XXXXXX")"
cleanup() { rm -rf "${work_dir}"; }
trap cleanup EXIT

hosted_zones_file="${work_dir}/hosted-zones.json"

log "Listing hosted zones"
aws route53 list-hosted-zones --output json > "${hosted_zones_file}" \
  || die "failed to list hosted zones"

zone_count="$(jq '.HostedZones | length' "${hosted_zones_file}")"
log "Found ${zone_count} hosted zone(s)"

while IFS= read -r zone_id; do
  short_id="${zone_id##*/}"
  log "Exporting records for ${short_id}"
  # aws cli v2 auto-paginates list-resource-record-sets.
  aws route53 list-resource-record-sets \
    --hosted-zone-id "${short_id}" \
    --output json > "${work_dir}/records-${short_id}.json" \
    || die "failed to list records for zone ${short_id}"
done < <(jq -r '.HostedZones[].Id' "${hosted_zones_file}")

log "Converting to ${out_dir}/zones.json"
# Optional in-scope allowlist: set IN_SCOPE_ZONES_FILE to a file of one domain
# per line to route any hosted zone outside the list to manual review instead
# of migrating it. Unset means migrate every (non-private) public zone.
convert_args=()
if [ -n "${IN_SCOPE_ZONES_FILE:-}" ]; then
  [ -f "${IN_SCOPE_ZONES_FILE}" ] || die "IN_SCOPE_ZONES_FILE not found: ${IN_SCOPE_ZONES_FILE}"
  convert_args+=(--in-scope-file "${IN_SCOPE_ZONES_FILE}")
  log "Restricting migration to in-scope zones from ${IN_SCOPE_ZONES_FILE}"
fi
PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" python3 -m migration convert \
  --zones "${hosted_zones_file}" \
  --records-dir "${work_dir}" \
  --output "${work_dir}/zones.json" \
  --review-output "${work_dir}/manual-review.json" \
  ${convert_args[@]+"${convert_args[@]}"}

# Publish only after a fully successful export + conversion.
mkdir -p "${out_dir}"
mv "${work_dir}/zones.json" "${out_dir}/zones.json"
mv "${work_dir}/manual-review.json" "${out_dir}/manual-review.json"

log "Wrote ${out_dir}/zones.json and ${out_dir}/manual-review.json"
