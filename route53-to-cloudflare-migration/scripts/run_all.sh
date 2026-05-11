#!/bin/bash
set -e

echo "Extract Route53 records to JSON"
python3 extract/export_route53_to_json.py


echo "Generating Terraform files"
mkdir -p terraform/data
if compgen -G "data/*.json" > /dev/null; then
  cp data/*.json terraform/data/
fi

cd terraform

echo "Running Terraform..."
terraform init -upgrade
terraform plan -out=tfplan
terraform apply -auto-approve tfplan