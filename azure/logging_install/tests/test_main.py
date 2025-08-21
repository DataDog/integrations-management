# stdlib
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock

# Needed to import the logging_install modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# project
import main
from errors import FatalError

# Test data
MANAGEMENT_GROUP_ID = "test-mg"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION = "test-sub-1"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = "sub-1,sub-2"
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"


class TestMain(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        # Set up mocks
        self.log_mock = self.patch("main.log")
        self.configuration_mock = self.patch("main.Configuration")
        self.set_subscription_mock = self.patch("main.set_subscription")
        self.validate_user_parameters_mock = self.patch("main.validate_user_parameters")
        self.create_resource_group_mock = self.patch("main.create_resource_group")
        self.grant_permissions_mock = self.patch("main.grant_permissions")
        self.deploy_control_plane_mock = self.patch("main.deploy_control_plane")
        self.run_initial_deploy_mock = self.patch("main.run_initial_deploy")
        self.basic_config_mock = self.patch("main.basicConfig")

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== Argument Parsing Tests ===== #

    def test_parse_arguments_with_required_params(self):
        """Test parsing arguments with all required parameters"""
        test_args = [
            "script.py",
            "--management-group",
            MANAGEMENT_GROUP_ID,
            "--control-plane-region",
            CONTROL_PLANE_REGION,
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION,
            "--control-plane-resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--monitored-subscriptions",
            MONITORED_SUBSCRIPTIONS,
            "--datadog-api-key",
            DATADOG_API_KEY,
        ]

        with mock_patch("sys.argv", test_args):
            args = main.parse_arguments()

        self.assertEqual(args.management_group, MANAGEMENT_GROUP_ID)
        self.assertEqual(args.control_plane_region, CONTROL_PLANE_REGION)
        self.assertEqual(args.control_plane_subscription, CONTROL_PLANE_SUBSCRIPTION)
        self.assertEqual(
            args.control_plane_resource_group, CONTROL_PLANE_RESOURCE_GROUP
        )
        self.assertEqual(args.monitored_subscriptions, MONITORED_SUBSCRIPTIONS)
        self.assertEqual(args.datadog_api_key, DATADOG_API_KEY)
        self.assertEqual(args.datadog_site, DATADOG_SITE)  # default value

    def test_parse_arguments_with_optional_params(self):
        """Test parsing arguments with optional parameters"""
        test_args = [
            "script.py",
            "--management-group",
            MANAGEMENT_GROUP_ID,
            "--control-plane-region",
            CONTROL_PLANE_REGION,
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION,
            "--control-plane-resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--monitored-subscriptions",
            MONITORED_SUBSCRIPTIONS,
            "--datadog-api-key",
            DATADOG_API_KEY,
            "--datadog-site",
            "datadoghq.eu",
            "--resource-tag-filters",
            "env:prod,team:infra",
            "--pii-scrubber-rules",
            "rules:\n  - pattern: test",
            "--datadog-telemetry",
            "--log-level",
            "DEBUG",
        ]

        with mock_patch("sys.argv", test_args):
            args = main.parse_arguments()

        self.assertEqual(args.datadog_site, "datadoghq.eu")
        self.assertEqual(args.resource_tag_filters, "env:prod,team:infra")
        self.assertEqual(args.pii_scrubber_rules, "rules:\n  - pattern: test")
        self.assertTrue(args.datadog_telemetry)
        self.assertEqual(args.log_level, "DEBUG")

    def test_parse_arguments_missing_required_param(self):
        """Test argument parsing fails when required parameter is missing"""
        test_args = [
            "script.py",
            "--management-group",
            MANAGEMENT_GROUP_ID,
            # Missing --control-plane-region
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION,
            "--control-plane-resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--monitored-subscriptions",
            MONITORED_SUBSCRIPTIONS,
            "--datadog-api-key",
            DATADOG_API_KEY,
        ]

        with mock_patch("sys.argv", test_args):
            with self.assertRaises(SystemExit):
                main.parse_arguments()

    def test_main_function_success(self):
        """Test overall successful execution"""
        # Mock Configuration creation
        mock_config = MagicMock()
        mock_config.log_level = "INFO"  # Ensure log_level is a string
        self.configuration_mock.return_value = mock_config

        # Mock args
        mock_args = MagicMock()
        mock_args.management_group = MANAGEMENT_GROUP_ID
        mock_args.control_plane_region = CONTROL_PLANE_REGION
        mock_args.control_plane_subscription = CONTROL_PLANE_SUBSCRIPTION
        mock_args.control_plane_resource_group = CONTROL_PLANE_RESOURCE_GROUP
        mock_args.monitored_subscriptions = MONITORED_SUBSCRIPTIONS
        mock_args.datadog_api_key = DATADOG_API_KEY
        mock_args.datadog_site = DATADOG_SITE
        mock_args.resource_tag_filters = ""
        mock_args.pii_scrubber_rules = ""
        mock_args.datadog_telemetry = False
        mock_args.log_level = "INFO"

        with mock_patch("main.parse_arguments", return_value=mock_args):
            main.main()

        # Verify the flow of function calls
        self.basic_config_mock.assert_called_once()
        self.configuration_mock.assert_called_once()
        self.validate_user_parameters_mock.assert_called_once_with(mock_config)
        self.create_resource_group_mock.assert_called_once_with(
            mock_config.control_plane_rg, mock_config.control_plane_region
        )
        self.grant_permissions_mock.assert_called_once_with(mock_config)
        self.deploy_control_plane_mock.assert_called_once_with(mock_config)
        self.run_initial_deploy_mock.assert_called_once_with(
            mock_config.deployer_job_name,
            mock_config.control_plane_rg,
            mock_config.control_plane_sub_id,
        )

    def test_main_function_handles_exceptions(self):
        """Test failed execution is handled properly"""
        # Mock Configuration to raise an exception
        self.configuration_mock.side_effect = FatalError("Test error")

        mock_args = MagicMock()
        with mock_patch("main.parse_arguments", return_value=mock_args):
            with self.assertRaises(FatalError):
                main.main()

        # Verify error logging
        self.log_mock.error.assert_called()
