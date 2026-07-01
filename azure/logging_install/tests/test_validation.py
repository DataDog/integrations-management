# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import (
    AccessError,
    AzCliNotAuthenticatedError,
    AzCliNotInstalledError,
    DatadogAccessValidationError,
    ExistenceCheckError,
    InputParamValidationError,
)
from common.datadog_validation import DatadogValidationError
from azure_logging_install import validation
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import REQUIRED_RESOURCE_PROVIDERS

from logging_install.tests.test_data import (
    CONTROL_PLANE_RESOURCE_GROUP,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    DATADOG_API_KEY,
    DATADOG_SITE,
    MONITORED_SUBSCRIPTIONS,
    SUB_1_ID,
    SUB_2_ID,
    SUB_3_ID,
    get_test_config,
    make_control_plane,
)

CONTROL_PLANE_CACHE_STORAGE_NAME = f"lfostorage{CONTROL_PLANE_SUBSCRIPTION_ID}"


def make_config(**overrides) -> Configuration:
    """Build a Configuration with default test settings, allowing overrides for specific fields
    (e.g. monitored_subs, resource_tag_filters, pii_scrubber_rules, control_plane)."""
    control_plane = overrides.pop("control_plane", None) or make_control_plane()
    defaults = {
        "control_plane": control_plane,
        "monitored_subs": MONITORED_SUBSCRIPTIONS,
        "datadog_api_key": DATADOG_API_KEY,
        "datadog_site": DATADOG_SITE,
    }
    defaults.update(overrides)
    return Configuration(**defaults)


class TestValidation(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.execute_mock = self.patch("azure_logging_install.validation.execute")
        self.set_subscription_mock = self.patch("azure_logging_install.validation.set_subscription")

        # Create test configuration
        self.config = get_test_config()

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== Main Validation Function Tests ===== #

    def test_validate_user_parameters_success(self):
        """Test successful validation of user parameters"""
        with (
            mock_patch("azure_logging_install.validation.validate_azure_env") as mock_azure,
            mock_patch("azure_logging_install.validation.validate_datadog_credentials") as mock_datadog,
        ):
            validation.validate_user_parameters(self.config)

            mock_azure.assert_called_once_with(self.config)
            mock_datadog.assert_called_once_with(self.config.datadog_api_key, self.config.datadog_site)

    def test_validate_user_parameters_azure_error(self):
        """Test validation fails when Azure validation fails"""
        with mock_patch(
            "azure_logging_install.validation.validate_azure_env",
            side_effect=AccessError("Azure error"),
        ):
            with self.assertRaises(AccessError):
                validation.validate_user_parameters(self.config)

    def test_validate_user_parameters_datadog_error(self):
        """Test validation fails when Datadog validation fails"""
        with (
            mock_patch("azure_logging_install.validation.validate_azure_env"),
            mock_patch(
                "azure_logging_install.validation.validate_datadog_credentials",
                side_effect=DatadogAccessValidationError("Datadog error"),
            ),
        ):
            with self.assertRaises(DatadogAccessValidationError):
                validation.validate_user_parameters(self.config)

    # ===== Azure CLI Validation Tests ===== #

    def test_validate_az_cli_success(self):
        """Test successful Azure CLI validation"""
        with mock_patch("azure_logging_install.validation.check_login", return_value="{}"):
            validation.validate_az_cli()

    def test_validate_az_cli_not_authenticated(self):
        """Test Azure CLI validation when not authenticated"""
        with mock_patch(
            "azure_logging_install.validation.check_login",
            side_effect=AzCliNotAuthenticatedError("not logged in"),
        ):
            with self.assertRaises(AzCliNotAuthenticatedError):
                validation.validate_az_cli()

    def test_validate_az_cli_not_installed(self):
        """Test Azure CLI validation when CLI is not installed"""
        with mock_patch(
            "azure_logging_install.validation.check_login",
            side_effect=AzCliNotInstalledError("az: command not found"),
        ):
            with self.assertRaises(AzCliNotInstalledError):
                validation.validate_az_cli()

    # ===== Subscription Access Validation Tests ===== #

    def test_validate_control_plane_sub_access_success(self):
        """Test successful control plane subscription access validation"""
        validation.validate_control_plane_sub_access(CONTROL_PLANE_SUBSCRIPTION_ID)

        self.set_subscription_mock.assert_called_once_with(CONTROL_PLANE_SUBSCRIPTION_ID)

    def test_validate_control_plane_sub_access_failure(self):
        """Test control plane subscription access validation failure"""
        self.set_subscription_mock.side_effect = AccessError("No access")

        with self.assertRaises(AccessError):
            validation.validate_control_plane_sub_access(CONTROL_PLANE_SUBSCRIPTION_ID)

    def test_validate_monitored_subs_access_success(self):
        """Test successful monitored subscriptions access validation"""
        validation.validate_monitored_subs_access([SUB_1_ID, SUB_2_ID])

        self.assertEqual(self.set_subscription_mock.call_count, 2)
        self.set_subscription_mock.assert_any_call(SUB_1_ID)
        self.set_subscription_mock.assert_any_call(SUB_2_ID)

    def test_validate_monitored_subs_access_partial_failure(self):
        """Test monitored subscriptions access validation with partial failure"""
        self.set_subscription_mock.side_effect = [
            None,
            AccessError("No access"),
        ]  # First succeeds, second fails

        with self.assertRaises(AccessError):
            validation.validate_monitored_subs_access([SUB_1_ID, SUB_2_ID])

    # ===== Resource Provider Registration Tests ===== #

    def test_validate_resource_provider_registrations_success(self):
        """Test successful resource provider registration validation"""
        mock_providers = [
            {"namespace": provider, "registrationState": "Registered"} for provider in REQUIRED_RESOURCE_PROVIDERS
        ]
        self.execute_mock.return_value = json.dumps(mock_providers)

        validation.validate_resource_provider_registrations({SUB_1_ID, SUB_2_ID})

        self.assertEqual(self.execute_mock.call_count, 2)

    def test_validate_resource_provider_registrations_multiple_subs(self):
        """Test resource provider registration validation for multiple subscriptions"""
        mock_providers = [
            {"namespace": provider, "registrationState": "Registered"} for provider in REQUIRED_RESOURCE_PROVIDERS
        ]
        self.execute_mock.return_value = json.dumps(mock_providers)

        validation.validate_resource_provider_registrations({SUB_1_ID, SUB_2_ID})

        self.assertEqual(self.execute_mock.call_count, 2)

    # ===== Resource Name Validation Tests ===== #

    def test_validate_resource_names_success(self):
        """Test successful resource name validation"""
        self.execute_mock.side_effect = [
            "false",
            json.dumps({"nameAvailable": True}),
        ]

        validation.validate_resource_names(
            CONTROL_PLANE_RESOURCE_GROUP,
            CONTROL_PLANE_SUBSCRIPTION_ID,
            CONTROL_PLANE_CACHE_STORAGE_NAME,
        )

        self.assertEqual(self.execute_mock.call_count, 2)

    def test_validate_resource_names_rg_exists(self):
        """Test resource name validation when resource group exists"""
        # Mock the execute calls for resource group check and storage name check
        self.execute_mock.side_effect = [
            "true",  # resource group exists (returned as string)
            json.dumps({"nameAvailable": True}),  # storage account check still happens
        ]

        try:
            validation.validate_resource_names(
                CONTROL_PLANE_RESOURCE_GROUP,
                CONTROL_PLANE_SUBSCRIPTION_ID,
                CONTROL_PLANE_CACHE_STORAGE_NAME,
            )
        except ExistenceCheckError:
            pass  # Expected if resource group exists

    def test_validate_resource_names_storage_unavailable(self):
        """Test resource name validation when storage account name is unavailable"""
        self.execute_mock.side_effect = [
            "false",  # resource group doesn't exist
            '{"nameAvailable": false, "reason": "AlreadyExists"}',  # storage unavailable
        ]

        try:
            validation.validate_resource_names(
                CONTROL_PLANE_RESOURCE_GROUP,
                CONTROL_PLANE_SUBSCRIPTION_ID,
                CONTROL_PLANE_CACHE_STORAGE_NAME,
            )
        except ExistenceCheckError:
            pass  # Expected if storage name is unavailable

    # ===== Datadog Credentials Validation Tests ===== #

    def test_validate_datadog_credentials_success(self):
        """Test successful Datadog credentials validation"""
        with mock_patch("azure_logging_install.validation.validate_api_key_v1", return_value=True):
            validation.validate_datadog_credentials(DATADOG_API_KEY, DATADOG_SITE)

    def test_validate_datadog_credentials_empty_key(self):
        """Test Datadog credentials validation with empty API key"""
        with self.assertRaises(InputParamValidationError):
            validation.validate_datadog_credentials("", DATADOG_SITE)

    def test_validate_datadog_credentials_invalid_api_key(self):
        """Test Datadog credentials validation with invalid API key"""
        with mock_patch(
            "azure_logging_install.validation.validate_api_key_v1",
            side_effect=DatadogValidationError("Invalid Datadog API key or site"),
        ):
            with self.assertRaises(DatadogAccessValidationError):
                validation.validate_datadog_credentials("invalid-key", DATADOG_SITE)

    def test_validate_datadog_credentials_delegates_to_shared(self):
        """Test that validation delegates to the shared validate_api_key_v1 function"""
        with mock_patch("azure_logging_install.validation.validate_api_key_v1", return_value=True) as mock_validate:
            validation.validate_datadog_credentials(DATADOG_API_KEY, "datadoghq.eu")
            mock_validate.assert_called_once_with(DATADOG_API_KEY, "datadoghq.eu")

    # ===== Azure Environment Validation Tests ===== #

    def test_validate_azure_env_success(self):
        """Test successful Azure environment validation"""
        with (
            mock_patch("azure_logging_install.validation.validate_user_config"),
            mock_patch("azure_logging_install.validation.validate_az_cli"),
            mock_patch("azure_logging_install.validation.validate_control_plane_sub_access"),
            mock_patch("azure_logging_install.validation.validate_monitored_subs_access"),
            mock_patch("azure_logging_install.validation.validate_resource_provider_registrations"),
            mock_patch("azure_logging_install.validation.validate_resource_names"),
        ):
            validation.validate_azure_env(self.config)

    def test_validate_azure_env_calls_all_validations(self):
        """Test Azure environment validation calls all required validations"""
        with (
            mock_patch("azure_logging_install.validation.validate_control_plane_sub_access") as mock_cp_access,
            mock_patch("azure_logging_install.validation.validate_monitored_subs_access") as mock_mon_access,
            mock_patch("azure_logging_install.validation.validate_resource_provider_registrations") as mock_rp_reg,
            mock_patch("azure_logging_install.validation.validate_resource_names") as mock_res_names,
        ):
            validation.validate_azure_env(self.config)

            mock_cp_access.assert_called_once_with(self.config.control_plane.subscription_id)
            mock_mon_access.assert_called_once_with(self.config.monitored_subscriptions)
            mock_rp_reg.assert_called_once_with(self.config.all_subscriptions)
            mock_res_names.assert_called_once()

    # ===== check_fresh_install Tests ===== #

    def test_check_fresh_install_no_existing_lfos(self):
        """Test no existing LFO installations found"""
        with mock_patch("azure_logging_install.validation.check_existing_lfo", return_value={}) as mock_check_existing:
            result = validation.check_fresh_install(self.config)

            self.assertEqual(result, {})
            mock_check_existing.assert_called_once_with(self.config.all_subscriptions)

    def test_check_fresh_install_with_existing_lfos(self):
        """Test existing LFO installations are found and returned"""
        existing_config_1 = make_config(
            control_plane=make_control_plane(id="abc123", resource_group="existing-rg", region="eastus"),
            monitored_subs=[SUB_1_ID, SUB_2_ID],
        )
        existing_config_2 = make_config(
            control_plane=make_control_plane(id="def456", resource_group="another-rg", region="westus"),
            monitored_subs=[SUB_3_ID],
        )
        mock_existing_lfos = {
            "abc123": existing_config_1,
            "def456": existing_config_2,
        }

        with mock_patch(
            "azure_logging_install.validation.check_existing_lfo",
            return_value=mock_existing_lfos,
        ) as mock_check_existing:
            result = validation.check_fresh_install(self.config)

            self.assertEqual(result, mock_existing_lfos)
            mock_check_existing.assert_called_once_with(self.config.all_subscriptions)

    # ===== validate_singleton_lfo Tests ===== #

    def test_validate_singleton_lfo_matching_id_does_not_exit(self):
        """Test validate_singleton_lfo does not exit when the single existing control plane ID matches"""
        existing_lfos = {self.config.control_plane.id: self.config}

        with mock_patch("azure_logging_install.validation.sys.exit") as mock_exit:
            validation.validate_singleton_lfo(self.config, existing_lfos)
            mock_exit.assert_not_called()

    def test_validate_singleton_lfo_mismatched_id_exits(self):
        """Test validate_singleton_lfo exits when the single existing control plane ID differs"""
        other_config = make_config(control_plane=make_control_plane(id="different-id"))
        existing_lfos = {"different-id": other_config}

        with mock_patch("azure_logging_install.validation.sys.exit") as mock_exit:
            validation.validate_singleton_lfo(self.config, existing_lfos)
            mock_exit.assert_called_once_with(0)

    def test_validate_singleton_lfo_multiple_existing_exits(self):
        """Test validate_singleton_lfo exits when more than one existing installation is found"""
        existing_lfos = {
            "abc123": make_config(control_plane=make_control_plane(id="abc123")),
            "def456": make_config(control_plane=make_control_plane(id="def456")),
        }

        with mock_patch("azure_logging_install.validation.sys.exit") as mock_exit:
            validation.validate_singleton_lfo(self.config, existing_lfos)
            mock_exit.assert_called_once_with(0)

    # ===== User Configuration Validation Tests ===== #

    def test_validate_user_config_success(self):
        """Test successful user configuration validation"""
        validation.validate_user_config(self.config)

    def test_control_plane_subscription_id_invalid(self):
        """Test validation fails with invalid control plane subscription IDs"""
        invalid_id_to_error_msg = {
            "not-a-uuid": "not a valid Azure subscription ID",
            "12345": "not a valid Azure subscription ID",
            "invalid-uuid-format": "not a valid Azure subscription ID",
            "1234abcd-1234-1234-1234": "not a valid Azure subscription ID",
            "gggggggg-1111-4111-a111-111111111111": "not a valid Azure subscription ID",
            "sss1iddd-58cc-4372-a567-0e02b2c3d479": "not a valid Azure subscription ID",
            "": "Control plane subscription cannot be empty",
            "  ": "Control plane subscription cannot be empty",
        }

        for invalid_id, expected_error in invalid_id_to_error_msg.items():
            with self.subTest(invalid_id=invalid_id):
                config = make_config(control_plane=make_control_plane(subscription_id=invalid_id))

                with self.assertRaises(InputParamValidationError) as context:
                    validation.validate_user_config(config)

                self.assertIn(expected_error, str(context.exception))

    def test_control_plane_subscription_id_valid(self):
        """Test validation succeeds with valid control plane subscription IDs"""
        valid_ids = [
            CONTROL_PLANE_SUBSCRIPTION_ID,
            "11111111-1111-4111-a111-111111111111",
            "aaaaaaaa-bbbb-4ccc-addd-eeeeeeeeeeee",
        ]

        for valid_id in valid_ids:
            with self.subTest(valid_id=valid_id):
                config = make_config(control_plane=make_control_plane(subscription_id=valid_id))

                validation.validate_user_config(config)

    def test_monitored_subscriptions_invalid(self):
        """Test validation fails with invalid monitored subscriptions"""
        invalid_subs_to_error_msg = {
            (): "no valid entries",
            ("",): "no valid entries",
            ("   ",): "no valid entries",
            (",", ",", ","): "not a valid Azure subscription ID",
            ("invalid-uuid", SUB_2_ID): "not a valid Azure subscription ID",
            (SUB_1_ID, "not-a-uuid"): "not a valid Azure subscription ID",
            ("sub1iddd-58cc-4372-a567-0e02b2c3d479",): "not a valid Azure subscription ID",
            ("12345", "67890"): "not a valid Azure subscription ID",
            ("gggggggg-1111-4111-a111-111111111111",): "not a valid Azure subscription ID",
            (SUB_1_ID, "invalid-uuid", SUB_2_ID): "not a valid Azure subscription ID",
        }

        for invalid_subs, expected_error in invalid_subs_to_error_msg.items():
            with self.subTest(invalid_subs=invalid_subs):
                config = make_config(monitored_subs=list(invalid_subs))

                with self.assertRaises(InputParamValidationError) as context:
                    validation.validate_user_config(config)

                self.assertIn(expected_error, str(context.exception))

    def test_monitored_subscriptions_valid(self):
        """Test validation succeeds with valid monitored subscriptions"""
        valid_subs = [
            MONITORED_SUBSCRIPTIONS,
            [SUB_1_ID],
            [SUB_1_ID, SUB_2_ID],
            [SUB_1_ID, SUB_2_ID, SUB_3_ID],
            [f"  {SUB_1_ID}  ", f"  {SUB_2_ID}  "],  # spaces will get stripped
        ]

        for valid_sub in valid_subs:
            with self.subTest(valid_sub=valid_sub):
                config = make_config(monitored_subs=valid_sub)

                validation.validate_user_config(config)

    # ===== Resource Tag Filters Validation Tests ===== #

    def test_tag_filters_invalid(self):
        """Test validation fails with invalid tag filters"""
        must_start_with_letter = "must start with a letter"
        invalid_filter_to_error_msg = {
            "1env:prod": must_start_with_letter,
            "123tag:value": must_start_with_letter,
            "9team:infra": must_start_with_letter,
            "0key:value": must_start_with_letter,
            "_env:prod": must_start_with_letter,
            "-team:infra": must_start_with_letter,
            "@tag:value": must_start_with_letter,
            "#key:value": must_start_with_letter,
            "$var:test": must_start_with_letter,
            "env:prod,1team:infra": must_start_with_letter,  # second tag invalid
            "valid:tag,_invalid:tag": must_start_with_letter,  # second tag invalid
            "9invalid:tag,another:valid": must_start_with_letter,  # first tag invalid
        }

        for invalid_filter, expected_error in invalid_filter_to_error_msg.items():
            with self.subTest(invalid_filter=invalid_filter):
                config = make_config(resource_tag_filters=invalid_filter)

                with self.assertRaises(InputParamValidationError) as context:
                    validation.validate_user_config(config)

                self.assertIn(expected_error, str(context.exception))

    def test_tag_filters_valid(self):
        """Test validation succeeds with valid tag filters"""
        valid_filters = [
            "",
            "env:prod",
            "Team:infra",
            "a1:value",
            "Z99:test",
            "Environment:production",
            "env:prod,team:infra",
            "key1:value1",
            "env:prod,team:infra,region:us-east",
            "tag1:value1,tag2:value2,tag3:value3",
            "justValue",
            "two,values",
            "!datadog:false",
        ]

        for valid_filter in valid_filters:
            with self.subTest(valid_filter=valid_filter):
                config = make_config(resource_tag_filters=valid_filter)

                # Should not raise an exception
                validation.validate_user_config(config)

    # ===== PII Scrubber Rules Validation Tests ===== #

    def test_pii_scrubber_rules_invalid(self):
        """Test validation fails with invalid PII scrubber rules"""
        invalid_rule_to_error_msg = {
            "invalid yaml without colons": "invalid YAML",
            "rule1\n  this is not valid yaml": "invalid YAML",
            "line without colon\nrule: value": "invalid YAML",
            "invalid line here\nvalid: line": "invalid YAML",
        }

        for invalid_rule, expected_error in invalid_rule_to_error_msg.items():
            with self.subTest(invalid_rule=invalid_rule):
                config = make_config(pii_scrubber_rules=invalid_rule)

                with self.assertRaises(InputParamValidationError) as context:
                    validation.validate_user_config(config)

                self.assertIn(expected_error, str(context.exception))

    def test_pii_scrubber_rules_valid(self):
        """Test validation succeeds with valid PII scrubber rules"""
        valid_rules = [
            "",  # empty string is optional
            "# This is a comment\n# Another comment",  # comments only
            "rule1: value1",
            "rule1:\n  pattern: 'sensitive data'\n  replacement: 'redacted'",
            "# This is a comment\nrule1: value1\nrule2: value2",
            "key: value\nkey2: value2\n# comment",
            "rule:\n  nested: value",
        ]

        for valid_rule in valid_rules:
            with self.subTest(valid_rule=valid_rule):
                config = make_config(pii_scrubber_rules=valid_rule)

                # Should not raise an exception
                validation.validate_user_config(config)
