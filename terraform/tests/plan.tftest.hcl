# Native Terraform tests. These use a mocked Cloudflare provider so no real
# resources are created and no credentials are needed.
#
# Run with:  terraform test   (requires access to the provider registry to
# install the cloudflare provider schema that the mock is built from).

mock_provider "cloudflare" {}

variables {
  cloudflare_account_id = "0123456789abcdef0123456789abcdef"
}

run "valid_input_creates_expected_resources" {
  command = plan

  variables {
    zones_file = "./tests/fixtures/valid.json"
  }

  assert {
    condition     = length(cloudflare_zone.zones) == 2
    error_message = "Expected two zones to be planned."
  }

  assert {
    condition     = length(cloudflare_dns_record.records) == 4
    error_message = "Expected four DNS records to be planned."
  }

  assert {
    condition     = cloudflare_dns_record.records["example.com|@|MX|mail.example.com|10"].priority == 10
    error_message = "MX priority was not propagated."
  }

  assert {
    condition     = cloudflare_dns_record.records["example.net|@|A|198.51.100.5|"].proxied == true
    error_message = "Explicit proxied=true was not honoured."
  }

  assert {
    condition     = cloudflare_dns_record.records["example.com|@|A|192.0.2.1|"].proxied == false
    error_message = "Records must default to unproxied."
  }
}

run "invalid_account_id_is_rejected" {
  command = plan

  variables {
    cloudflare_account_id = "not-a-valid-id"
    zones_file            = "./tests/fixtures/valid.json"
  }

  expect_failures = [var.cloudflare_account_id]
}

run "empty_zones_blocks_apply" {
  command = plan

  variables {
    zones_file = "./tests/fixtures/empty.json"
  }

  expect_failures = [terraform_data.guard]
}
