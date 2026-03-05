# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest

from gcp_agentless_setup.config import Config
from gcp_agentless_setup.terraform import (
    _abbreviate_region,
    generate_terraform_config,
    generate_tfvars,
    MODULE_VERSION,
    MODULE_SOURCE_SCANNER_SA,
)


# Test fixture for api_key_secret_id
TEST_API_KEY_SECRET_ID = "projects/scanner-project/secrets/datadog-agentless-scanner-api-key"


class TestGenerateTerraformConfig(unittest.TestCase):
    """Test Terraform configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config(
            api_key="test-api-key",
            app_key="test-app-key",
            site="datadoghq.com",
            scanner_project="scanner-project",
            regions=["us-central1"],
            projects_to_scan=["scanner-project", "other-project"],
            workflow_id="test-workflow-id",
        )

    def test_generates_backend_config(self):
        """Test that backend configuration is generated correctly."""
        tf = generate_terraform_config(self.config, "my-state-bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('bucket = "my-state-bucket"', tf)
        self.assertIn('prefix = "datadog-agentless"', tf)

    def test_generates_default_provider(self):
        """Test that a default (un-aliased) Google provider is generated for project-scoped resources."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have a default provider block without alias
        self.assertIn('# Default provider for project-scoped resources', tf)
        # The default provider should reference the scanner project
        self.assertIn('project = "scanner-project"', tf)

    def test_generates_scanner_project_provider(self):
        """Test that scanner project provider is generated with region alias."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('project = "scanner-project"', tf)
        self.assertIn('region  = "us-central1"', tf)
        self.assertIn('alias   = "us_central1"', tf)

    def test_generates_other_project_providers(self):
        """Test that providers for other projects are generated with aliases."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Other project should have aliased provider
        self.assertIn('alias   = "other_project"', tf)
        self.assertIn('project = "other-project"', tf)

    def test_generates_scanner_service_account_module(self):
        """Test that an explicit scanner service account module is generated."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('module "scanner_service_account"', tf)
        self.assertIn(MODULE_SOURCE_SCANNER_SA, tf)
        self.assertIn(f'api_key_secret_id = "{TEST_API_KEY_SECRET_ID}"', tf)

    def test_generates_impersonated_sa_for_scanner_project(self):
        """Test that an impersonated SA module is generated for the scanner project."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('module "impersonated_service_account"', tf)
        self.assertIn(
            "scanner_service_account_email = module.scanner_service_account.scanner_service_account_email",
            tf,
        )

    def test_generates_impersonated_sa_modules(self):
        """Test that impersonated SA modules are generated for other projects."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have module for other project
        self.assertIn('module "agentless_impersonated_sa_other_project"', tf)
        self.assertIn("google = google.other_project", tf)
        # Should reference the explicit scanner SA, not a region-specific one
        self.assertIn(
            "scanner_service_account_email = module.scanner_service_account.scanner_service_account_email",
            tf,
        )
        self.assertNotIn("module.datadog_agentless_us", tf)

    def test_regional_modules_pass_scanner_service_account_email(self):
        """Test that regional scanner modules reference the shared scanner SA."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('module "datadog_agentless_us_central1"', tf)
        self.assertIn(
            "scanner_service_account_email = module.scanner_service_account.scanner_service_account_email",
            tf,
        )

    def test_generates_scan_options_for_all_projects(self):
        """Test that scan options are generated for all projects."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Scanner project scan options
        self.assertIn(
            'resource "datadog_agentless_scanning_gcp_scan_options" "scanner_project"',
            tf,
        )
        self.assertIn('gcp_project_id     = "scanner-project"', tf)

        # Other project scan options
        self.assertIn(
            'resource "datadog_agentless_scanning_gcp_scan_options" "scan_other_project"',
            tf,
        )
        self.assertIn('gcp_project_id     = "other-project"', tf)

    def test_no_extra_project_providers_when_only_scanner(self):
        """Test no aliased providers for other projects when only scanning scanner project."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="only-project",
            regions=["us-central1"],
            projects_to_scan=["only-project"],
            workflow_id="test-workflow-id",
        )

        tf = generate_terraform_config(config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have region alias but not project alias
        self.assertIn('alias   = "us_central1"', tf)
        # Should not have impersonated SA modules for other projects
        self.assertNotIn("agentless_impersonated_sa_", tf)
        # Should still have scanner SA and impersonated SA for scanner project
        self.assertIn('module "scanner_service_account"', tf)
        self.assertIn('module "impersonated_service_account"', tf)

    def test_generates_multiple_region_providers_and_modules(self):
        """Test that multiple regions generate multiple providers and scanner modules."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-project",
            regions=["us-central1", "europe-west1"],
            projects_to_scan=["scanner-project"],
            workflow_id="test-workflow-id",
        )

        tf = generate_terraform_config(config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have provider for each region
        self.assertIn('alias   = "us_central1"', tf)
        self.assertIn('alias   = "europe_west1"', tf)
        self.assertIn('region  = "us-central1"', tf)
        self.assertIn('region  = "europe-west1"', tf)

        # Should have scanner module for each region
        self.assertIn('module "datadog_agentless_us_central1"', tf)
        self.assertIn('module "datadog_agentless_europe_west1"', tf)

        # VPC names use abbreviated regions to stay within GCP's 63-char limit
        self.assertIn('vpc_name                      = "datadog-agentless-us-cen1"', tf)
        self.assertIn('vpc_name                      = "datadog-agentless-eu-west1"', tf)

        # Both regional modules should share the same scanner SA
        # Count occurrences of the SA reference - should appear in
        # impersonated_sa module (1) and each regional module (2) = 3 total
        sa_ref = "module.scanner_service_account.scanner_service_account_email"
        self.assertGreaterEqual(tf.count(sa_ref), 3)

    def test_uses_correct_module_version(self):
        """Test that the correct module version is used."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn(f"ref={MODULE_VERSION}", tf)

    def test_uses_api_key_secret_id_not_raw_key(self):
        """Test that api_key_secret_id is used instead of raw api_key."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should use api_key_secret_id in module
        self.assertIn(f'api_key_secret_id = "{TEST_API_KEY_SECRET_ID}"', tf)

        # Should NOT have raw api_key variable
        self.assertNotIn('variable "datadog_api_key"', tf)

        # Should NOT have api_key in module
        self.assertNotIn("api_key  =", tf)


class TestAbbreviateRegion(unittest.TestCase):
    """Test region name abbreviation for GCP resource name limits."""

    def test_short_regions_partially_abbreviated(self):
        self.assertEqual(_abbreviate_region("us-east1"), "us-east1")
        self.assertEqual(_abbreviate_region("us-west4"), "us-west4")
        self.assertEqual(_abbreviate_region("me-west1"), "me-west1")
        self.assertEqual(_abbreviate_region("us-south1"), "us-south1")
        self.assertEqual(_abbreviate_region("us-central1"), "us-cen1")

    def test_long_continents_abbreviated(self):
        self.assertEqual(_abbreviate_region("europe-west1"), "eu-west1")
        self.assertEqual(_abbreviate_region("europe-north1"), "eu-north1")
        self.assertEqual(_abbreviate_region("australia-southeast1"), "au-se1")
        self.assertEqual(_abbreviate_region("northamerica-northeast1"), "na-ne1")
        self.assertEqual(_abbreviate_region("southamerica-east1"), "sa-east1")
        self.assertEqual(_abbreviate_region("africa-south1"), "af-south1")

    def test_compound_directions_abbreviated(self):
        self.assertEqual(_abbreviate_region("europe-southwest1"), "eu-sw1")
        self.assertEqual(_abbreviate_region("asia-southeast1"), "asia-se1")
        self.assertEqual(_abbreviate_region("asia-northeast1"), "asia-ne1")
        self.assertEqual(_abbreviate_region("northamerica-northeast2"), "na-ne2")

    def test_all_abbreviated_vpc_names_fit_63_char_limit(self):
        """The TF module appends -{8char_suffix}-allow-health-checks (+30 chars)."""
        long_regions = [
            "northamerica-northeast1",
            "northamerica-northeast2",
            "northamerica-south1",
            "southamerica-east1",
            "southamerica-west1",
            "australia-southeast1",
            "australia-southeast2",
            "europe-southwest1",
            "asia-southeast1",
            "asia-southeast2",
            "asia-northeast1",
            "asia-northeast2",
            "asia-northeast3",
        ]
        for region in long_regions:
            vpc_name = f"datadog-agentless-{_abbreviate_region(region)}"
            worst_case = f"{vpc_name}-{'a' * 8}-allow-health-checks"
            self.assertLessEqual(
                len(worst_case), 63,
                f"Region {region} → vpc_name '{vpc_name}' produces "
                f"'{worst_case}' ({len(worst_case)} chars, exceeds 63)",
            )


class TestGenerateTfvars(unittest.TestCase):
    """Test terraform.tfvars generation."""

    def test_generates_tfvars_with_credentials(self):
        """Test that tfvars contains app_key and site but not api_key."""
        config = Config(
            api_key="my-api-key",
            app_key="my-app-key",
            site="us5.datadoghq.com",
            scanner_project="proj",
            regions=["us-central1"],
            projects_to_scan=["proj"],
            workflow_id="test-workflow-id",
        )

        tfvars = generate_tfvars(config)

        # API key should NOT be in tfvars (stored in Secret Manager)
        self.assertNotIn("datadog_api_key", tfvars)
        self.assertNotIn("my-api-key", tfvars)

        # App key and site should still be present
        self.assertIn('datadog_app_key = "my-app-key"', tfvars)
        self.assertIn('datadog_site    = "us5.datadoghq.com"', tfvars)


if __name__ == "__main__":
    unittest.main()
