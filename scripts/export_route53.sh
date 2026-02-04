#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:-data}"
mkdir -p "${out_dir}"

hosted_zones_file="${out_dir}/hosted-zones.json"

aws route53 list-hosted-zones --output json > "${hosted_zones_file}"

while IFS= read -r zone_id; do
  short_id="${zone_id##*/}"
  aws route53 list-resource-record-sets \
    --hosted-zone-id "${short_id}" \
    --output json > "${out_dir}/records-${short_id}.json"
done < <(jq -r '.HostedZones[].Id' "${hosted_zones_file}")

python3 scripts/route53_to_cloudflare.py \
  --zones "${hosted_zones_file}" \
  --records-dir "${out_dir}" \
  --output "${out_dir}/zones.json" \
  --alias-output "${out_dir}/alias-records.json"

echo "Wrote ${out_dir}/zones.json and ${out_dir}/alias-records.json"
