# stdlib
# stdlib
import json
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock

# project
from azure_logging_install import validation
from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import REQUIRED_RESOURCE_PROVIDERS
from azure_logging_install.errors import (
    AccessError,
    DatadogAccessValidationError,
    ExistenceCheckError,
    InputParamValidationError,
    ResourceProviderRegistrationValidationError,
)

# Test data
MANAGEMENT_GROUP_ID = "test-mg"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION = "test-sub-1"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = "sub-1,sub-2"
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"

MOCK_DATADOG_VALID_RESPONSE = {
    "valid": True,
}

MOCK_DATADOG_ERROR_RESPONSE = {
    "status": "error",
    "code": 403,
    "errors": ["Forbidden"],
}


class TestValidation(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.execute_mock = self.patch("azure_logging_install.validation.execute")
        self.set_subscription_mock = self.patch(
            "azure_logging_install.validation.set_subscription"
        )
        self.urlopen_mock = self.patch(
            "azure_logging_install.validation.urllib.request.urlopen"
        )

        # Create test configuration
        self.config = Configuration(
            management_group_id=MANAGEMENT_GROUP_ID,
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION,
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
            datadog_site=DATADOG_SITE,
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== Main Validation Function Tests ===== #

    def test_validate_user_parameters_success(self):
        """Test successful validation of user parameters"""
        with (
            mock_patch(
                "azure_logging_install.validation.validate_azure_env"
            ) as mock_azure,
            mock_patch(
                "azure_logging_install.validation.validate_datadog_credentials"
            ) as mock_datadog,
        ):
            validation.validate_user_parameters(self.config)

            mock_azure.assert_called_once_with(self.config)
            mock_datadog.assert_called_once_with(DATADOG_API_KEY, DATADOG_SITE)

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
        self.execute_mock.return_value = "azure-cli-user"

        validation.validate_az_cli()

        self.execute_mock.assert_called_once()

    def test_validate_az_cli_not_authenticated(self):
        """Test Azure CLI validation when not authenticated"""
        self.execute_mock.side_effect = Exception("Please run 'az login'")

        with self.assertRaises(AccessError) as context:
            validation.validate_az_cli()

        self.assertIn("Azure CLI not authenticated", str(context.exception))

    # ===== User Configuration Validation Tests ===== #

    def test_validate_user_config_success(self):
        """Test successful user configuration validation"""
        validation.validate_user_config(self.config)

    def test_validate_user_config_empty_management_group(self):
        """Test validation fails with empty management group"""
        config = Configuration(
            management_group_id="",
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION,
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
        )

        with self.assertRaises(InputParamValidationError):
            validation.validate_user_config(config)

    def test_validate_user_config_empty_monitored_subs(self):
        """Test validation fails with empty monitored subscriptions"""
        config = Configuration(
            management_group_id=MANAGEMENT_GROUP_ID,
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION,
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs="",
            datadog_api_key=DATADOG_API_KEY,
        )

        with self.assertRaises(InputParamValidationError):
            validation.validate_user_config(config)

    # ===== Subscription Access Validation Tests ===== #

    def test_validate_control_plane_sub_access_success(self):
        """Test successful control plane subscription access validation"""
        validation.validate_control_plane_sub_access(CONTROL_PLANE_SUBSCRIPTION)

        self.set_subscription_mock.assert_called_once_with(CONTROL_PLANE_SUBSCRIPTION)

    def test_validate_control_plane_sub_access_failure(self):
        """Test control plane subscription access validation failure"""
        self.set_subscription_mock.side_effect = AccessError("No access")

        with self.assertRaises(AccessError):
            validation.validate_control_plane_sub_access(CONTROL_PLANE_SUBSCRIPTION)

    def test_validate_monitored_subs_access_success(self):
        """Test successful monitored subscriptions access validation"""
        validation.validate_monitored_subs_access(["sub-1", "sub-2"])

        self.assertEqual(self.set_subscription_mock.call_count, 2)
        self.set_subscription_mock.assert_any_call("sub-1")
        self.set_subscription_mock.assert_any_call("sub-2")

    def test_validate_monitored_subs_access_partial_failure(self):
        """Test monitored subscriptions access validation with partial failure"""
        self.set_subscription_mock.side_effect = [
            None,
            AccessError("No access"),
        ]  # First succeeds, second fails

        with self.assertRaises(AccessError):
            validation.validate_monitored_subs_access(["sub-1", "sub-2"])

    # ===== Resource Provider Registration Tests ===== #

    def test_validate_resource_provider_registrations_success(self):
        """Test successful resource provider registration validation"""
        mock_providers = [
            {"namespace": provider, "registrationState": "Registered"}
            for provider in REQUIRED_RESOURCE_PROVIDERS
        ]
        self.execute_mock.return_value = json.dumps(mock_providers)

        validation.validate_resource_provider_registrations({"sub-1", "sub-2"})

        self.assertEqual(self.execute_mock.call_count, 2)

    def test_validate_resource_provider_registrations_not_registered(self):
        """Test resource provider registration validation failure"""
        mock_providers = [
            {"namespace": "Microsoft.Web", "registrationState": "NotRegistered"},
            {"namespace": "Microsoft.App", "registrationState": "Registered"},
        ]
        self.execute_mock.return_value = json.dumps(mock_providers)

        with self.assertRaises(ResourceProviderRegistrationValidationError):
            validation.validate_resource_provider_registrations({"sub-1"})

    def test_validate_resource_provider_registrations_multiple_subs(self):
        """Test resource provider registration validation for multiple subscriptions"""
        mock_providers = [
            {"namespace": provider, "registrationState": "Registered"}
            for provider in REQUIRED_RESOURCE_PROVIDERS
        ]
        self.execute_mock.return_value = json.dumps(mock_providers)

        validation.validate_resource_provider_registrations({"sub-1", "sub-2"})

        self.assertEqual(self.execute_mock.call_count, 2)

    # ===== Resource Name Validation Tests ===== #

    def test_validate_resource_names_success(self):
        """Test successful resource name validation"""
        self.execute_mock.side_effect = [
            "false",
            json.dumps({"nameAvailable": True}),
        ]

        validation.validate_resource_names(
            CONTROL_PLANE_RESOURCE_GROUP, CONTROL_PLANE_SUBSCRIPTION, "teststorage123"
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
                CONTROL_PLANE_SUBSCRIPTION,
                "teststorage123",
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
                CONTROL_PLANE_SUBSCRIPTION,
                "teststorage123",
            )
        except ExistenceCheckError:
            pass  # Expected if storage name is unavailable

    # ===== Datadog Credentials Validation Tests ===== #

    def test_validate_datadog_credentials_success(self):
        """Test successful Datadog credentials validation"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            MOCK_DATADOG_VALID_RESPONSE
        ).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        self.urlopen_mock.return_value = mock_response
        validation.validate_datadog_credentials(DATADOG_API_KEY, DATADOG_SITE)

    def test_validate_datadog_credentials_invalid_api_key(self):
        """Test Datadog credentials validation with invalid API key"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            MOCK_DATADOG_ERROR_RESPONSE
        ).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        self.urlopen_mock.return_value = mock_response

        with self.assertRaises(DatadogAccessValidationError):
            validation.validate_datadog_credentials("invalid-key", DATADOG_SITE)

    def test_validate_datadog_credentials_different_sites(self):
        """Test Datadog credentials validation with different sites"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            MOCK_DATADOG_VALID_RESPONSE
        ).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        self.urlopen_mock.return_value = mock_response

        validation.validate_datadog_credentials(DATADOG_API_KEY, "datadoghq.eu")
        if self.urlopen_mock.call_args:
            call_args = self.urlopen_mock.call_args[0][0]
            self.assertIn("datadoghq.eu", call_args.full_url)

    # ===== Azure Environment Validation Tests ===== #

    def test_validate_azure_env_success(self):
        """Test successful Azure environment validation"""
        with (
            mock_patch("azure_logging_install.validation.validate_user_config"),
            mock_patch("azure_logging_install.validation.validate_az_cli"),
            mock_patch(
                "azure_logging_install.validation.validate_control_plane_sub_access"
            ),
            mock_patch(
                "azure_logging_install.validation.validate_monitored_subs_access"
            ),
            mock_patch(
                "azure_logging_install.validation.validate_resource_provider_registrations"
            ),
            mock_patch("azure_logging_install.validation.validate_resource_names"),
        ):
            validation.validate_azure_env(self.config)

    def test_validate_azure_env_calls_all_validations(self):
        """Test Azure environment validation calls all required validations"""
        with (
            mock_patch(
                "azure_logging_install.validation.validate_control_plane_sub_access"
            ) as mock_cp_access,
            mock_patch(
                "azure_logging_install.validation.validate_monitored_subs_access"
            ) as mock_mon_access,
            mock_patch(
                "azure_logging_install.validation.validate_resource_provider_registrations"
            ) as mock_rp_reg,
            mock_patch(
                "azure_logging_install.validation.validate_resource_names"
            ) as mock_res_names,
        ):
            validation.validate_azure_env(self.config)

            mock_cp_access.assert_called_once_with(self.config.control_plane_sub_id)
            mock_mon_access.assert_called_once_with(self.config.monitored_subscriptions)
            mock_rp_reg.assert_called_once_with(self.config.all_subscriptions)
            mock_res_names.assert_called_once()
