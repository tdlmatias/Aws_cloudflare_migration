#!/bin/bash
set -e

echo "Extract Route53 records to JSON"
python3 extract/extract_route53_to_json.py


echo "Generating Terraform files"
cp data/*.json terraform/data/

cd terraform

echo "Running Terraform..."
terraform init -upgrade
terraform plan -out=tfplan
terraform apply -auto-approve tfplan