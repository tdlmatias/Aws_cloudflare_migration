import boto3
import json
import os
import logging
from botocore.exceptions import ClientError

# Logging setup
logging.basicConfig(filename='logs/migrating.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# AWS client setup
route53_client = boto3.client('route53')

def get_hosted_zones():
    zones = []
    paginator = route53_client.get_paginator('list_hosted_zones')
    for page in paginator.paginate():
        zones.extend(page['HostedZones'])
    return zones

def get_dns_records(zone_id): 
    records = []
    paginator = route53_client.get_paginator('list_resource_record_sets')
    for page in paginator.paginate(HostedZoneId=zone_id):
        records.extend(page['ResourceRecordSets'])
    return records

def transform_record(record):
    cf_records = []
    for record in records:
        if record['Type'] in ['NS', 'SOA']:
            continue # Cloudflare Manages NS and SOA records automatically
        entry = {
            "type": record['Type'],
            "name": record['Name'].rstrip('.'),
            "ttl": record.get('TTL', 300),
        }
        
        # A, AAAA, CNAME, and other simple record types
        values = []
        for r in record.get('ResourceRecords', []):
            values.append(r['Value'])
            
        if record['Type'] == 'MX':
            values = [f"{r['Priority']} {r['Value']}" for r in record['ResourceRecords']] # Sort MX records by priority
            
        entry['content'] = values if len(values) > 1 else values[0]
        
        cf_records.append(entry)
    return cf_records


def write_to_json(domain, records):
    os.makedirs('data', exist_ok=True)
    path = f'data/{domain}.json'
    with open(path, 'w') as f:
        json.dump(records, f, indent=2)
    logging.info(f"Exported {len(records)} records for {domain} to {path}")
    
    
def main():
    zones = get_hosted_zones()
    logging.info(f"Found {len(zones)} hosted zones in Route53")
    
    for zone in zones:
        zone_id = zone['Id'].split('/')[-1]
        domain_name = zone['Name'].rstrip('.')
        logging.info(f"Processing hosted zone: {domain_name} (ID: {zone_id})")
        
        try:
            records = get_dns_records(zone['Id'])
            transformed = transform_record(records)
            write_to_json(domain_name, transformed)
            logging.info(f"✅ Exported {len(transformed)} records for {domain_name}")
        except ClientError as e:
            logging.error(f"❌ Failed to get records for {domain_name}: {e}")
            
if __name__ == "__main__":
    main()