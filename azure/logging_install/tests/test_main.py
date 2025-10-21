# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from az_shared.errors import FatalError, InputParamValidationError
from azure_logging_install import main
from azure_logging_install.existing_lfo import LfoControlPlane, LfoMetadata, update_existing_lfo

from logging_install.tests.test_data import (
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    CONTROL_PLANE_SUBSCRIPTION_NAME,
    DATADOG_API_KEY,
    DATADOG_SITE,
    DEPLOYER_JOB_NAME,
    DIAGNOSTIC_SETTINGS_TASK_NAME,
    MONITORED_SUBSCRIPTIONS,
    PII_SCRUBBER_RULES,
    RESOURCE_TAG_FILTERS,
    RESOURCE_TASK_NAME,
    SCALING_TASK_NAME,
    SUB_1_ID,
    SUB_2_ID,
    SUB_3_ID,
    SUB_ID_TO_NAME,
    get_test_config,
)


class TestMain(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.configuration_mock = self.patch("azure_logging_install.main.Configuration")
        self.set_subscription_mock = self.patch("azure_logging_install.main.set_subscription")
        self.validate_user_parameters_mock = self.patch("azure_logging_install.main.validate_user_parameters")
        self.create_resource_group_mock = self.patch("azure_logging_install.main.create_resource_group")
        self.grant_permissions_mock = self.patch("azure_logging_install.main.grant_permissions")
        self.deploy_control_plane_mock = self.patch("azure_logging_install.main.deploy_control_plane")
        self.run_initial_deploy_mock = self.patch("azure_logging_install.main.run_initial_deploy")

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
            "--control-plane-region",
            CONTROL_PLANE_REGION,
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION_ID,
            "--control-plane-resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--monitored-subscriptions",
            MONITORED_SUBSCRIPTIONS,
            "--datadog-api-key",
            DATADOG_API_KEY,
        ]

        with mock_patch("sys.argv", test_args):
            args = main.parse_arguments()

        self.assertEqual(args.control_plane_region, CONTROL_PLANE_REGION)
        self.assertEqual(args.control_plane_subscription, CONTROL_PLANE_SUBSCRIPTION_ID)
        self.assertEqual(args.control_plane_resource_group, CONTROL_PLANE_RESOURCE_GROUP)
        self.assertEqual(args.monitored_subscriptions, MONITORED_SUBSCRIPTIONS)
        self.assertEqual(args.datadog_api_key, DATADOG_API_KEY)
        self.assertEqual(args.datadog_site, DATADOG_SITE)

    def test_parse_arguments_with_optional_params(self):
        """Test parsing arguments with optional parameters"""
        test_args = [
            "script.py",
            "--control-plane-region",
            CONTROL_PLANE_REGION,
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION_ID,
            "--control-plane-resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--monitored-subscriptions",
            MONITORED_SUBSCRIPTIONS,
            "--datadog-api-key",
            DATADOG_API_KEY,
            "--datadog-site",
            "datadoghq.eu",
            "--resource-tag-filters",
            RESOURCE_TAG_FILTERS,
            "--pii-scrubber-rules",
            PII_SCRUBBER_RULES,
            "--datadog-telemetry",
            "--log-level",
            "DEBUG",
        ]

        with mock_patch("sys.argv", test_args):
            args = main.parse_arguments()

        self.assertEqual(args.datadog_site, "datadoghq.eu")
        self.assertEqual(args.resource_tag_filters, RESOURCE_TAG_FILTERS)
        self.assertEqual(args.pii_scrubber_rules, PII_SCRUBBER_RULES)
        self.assertTrue(args.datadog_telemetry)
        self.assertEqual(args.log_level, "DEBUG")

    def test_parse_arguments_missing_required_param(self):
        """Test argument parsing fails when required parameter is missing"""
        test_args = [
            "script.py",
            # Missing --control-plane-region
            "--control-plane-subscription",
            CONTROL_PLANE_SUBSCRIPTION_ID,
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
        mock_config = MagicMock()
        mock_config.log_level = "INFO"
        self.configuration_mock.return_value = mock_config

        mock_args = MagicMock()
        mock_args.control_plane_region = CONTROL_PLANE_REGION
        mock_args.control_plane_subscription = CONTROL_PLANE_SUBSCRIPTION_ID
        mock_args.control_plane_resource_group = CONTROL_PLANE_RESOURCE_GROUP
        mock_args.monitored_subscriptions = MONITORED_SUBSCRIPTIONS
        mock_args.datadog_api_key = DATADOG_API_KEY
        mock_args.datadog_site = DATADOG_SITE
        mock_args.resource_tag_filters = RESOURCE_TAG_FILTERS
        mock_args.pii_scrubber_rules = PII_SCRUBBER_RULES
        mock_args.datadog_telemetry = False
        mock_args.log_level = "INFO"

        with mock_patch("azure_logging_install.main.parse_arguments", return_value=mock_args):
            main.main()

        # Verify the flow of function calls
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
        with mock_patch("azure_logging_install.main.parse_arguments", return_value=mock_args):
            with self.assertRaises(InputParamValidationError):
                main.main()

    # ===== Integration Flow Tests ===== #

    def test_create_new_lfo_success(self):
        """Test successful creation of new LFO installation"""
        mock_config = MagicMock()
        mock_config.control_plane_sub_id = CONTROL_PLANE_SUBSCRIPTION_ID
        mock_config.control_plane_rg = CONTROL_PLANE_RESOURCE_GROUP
        mock_config.control_plane_region = CONTROL_PLANE_REGION
        mock_config.deployer_job_name = DEPLOYER_JOB_NAME

        main.create_new_lfo(mock_config)

        # Verify all steps are called in correct order
        self.set_subscription_mock.assert_called_once_with(CONTROL_PLANE_SUBSCRIPTION_ID)
        self.create_resource_group_mock.assert_called_once_with(CONTROL_PLANE_RESOURCE_GROUP, CONTROL_PLANE_REGION)
        self.deploy_control_plane_mock.assert_called_once_with(mock_config)
        self.grant_permissions_mock.assert_called_once_with(mock_config)
        self.run_initial_deploy_mock.assert_called_once_with(
            DEPLOYER_JOB_NAME,
            CONTROL_PLANE_RESOURCE_GROUP,
            CONTROL_PLANE_SUBSCRIPTION_ID,
        )

    def test_create_new_lfo_handles_errors(self):
        """Test create_new_lfo handles errors properly"""
        mock_config = MagicMock()
        error_message = "Resource group creation failed"
        self.create_resource_group_mock.side_effect = FatalError(error_message)

        with self.assertRaises(FatalError) as context:
            main.create_new_lfo(mock_config)

        self.assertEqual(str(context.exception), error_message)
        self.deploy_control_plane_mock.assert_not_called()
        self.grant_permissions_mock.assert_not_called()
        self.run_initial_deploy_mock.assert_not_called()

    def test_update_existing_lfo_subs_and_settings(self):
        """Test successful update of existing LFO installation where a new subscription and new tag filters are specified"""

        # Mock represents the new incoming config with an additional subscription (sub 3) and new tag filters
        mock_config = MagicMock()
        mock_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID, SUB_3_ID]
        mock_config.control_plane_function_app_names = [
            RESOURCE_TASK_NAME,
            SCALING_TASK_NAME,
            DIAGNOSTIC_SETTINGS_TASK_NAME,
        ]
        mock_config.resource_tag_filters = RESOURCE_TAG_FILTERS
        mock_config.pii_scrubber_rules = PII_SCRUBBER_RULES

        # Existing LFO with a missing sub and different tag filter
        existing_lfos = {
            CONTROL_PLANE_ID: LfoMetadata(
                control_plane=LfoControlPlane(
                    CONTROL_PLANE_SUBSCRIPTION_ID,
                    CONTROL_PLANE_SUBSCRIPTION_NAME,
                    CONTROL_PLANE_RESOURCE_GROUP,
                    CONTROL_PLANE_REGION,
                ),
                monitored_subs={
                    SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                    SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
                },
                tag_filter="env:staging",
                pii_rules=PII_SCRUBBER_RULES,
            )
        }

        with (
            mock_patch("azure_logging_install.existing_lfo.set_function_app_env_vars") as mock_set_env_vars,
            mock_patch("azure_logging_install.existing_lfo.grant_subscriptions_permissions") as mock_grant_subs_perms,
        ):
            existing_lfo = next(iter(existing_lfos.values()))
            update_existing_lfo(mock_config, existing_lfo)

            # Verify function app environment variables are updated due to new tag filter
            self.assertEqual(mock_set_env_vars.call_count, 3)
            mock_set_env_vars.assert_any_call(mock_config, RESOURCE_TASK_NAME)
            mock_set_env_vars.assert_any_call(mock_config, SCALING_TASK_NAME)
            mock_set_env_vars.assert_any_call(mock_config, DIAGNOSTIC_SETTINGS_TASK_NAME)

            # Verify permissions are granted only for new subscription
            mock_grant_subs_perms.assert_called_once_with(mock_config, {SUB_3_ID})

    def test_install_log_forwarder_new_installation(self):
        """Test install_log_forwarder flow for new installation"""
        test_config = get_test_config()

        with (
            mock_patch("azure_logging_install.main.validate_az_cli") as mock_validate_cli,
            mock_patch("azure_logging_install.main.validate_user_parameters") as mock_validate_params,
            mock_patch("azure_logging_install.main.list_users_subscriptions") as mock_list_subs,
            mock_patch("azure_logging_install.main.check_fresh_install") as mock_check_fresh,
            mock_patch("azure_logging_install.main.create_new_lfo") as mock_create_new,
        ):
            mock_list_subs.return_value = SUB_ID_TO_NAME
            mock_check_fresh.return_value = {}  # No existing LFOs found

            # Execute the function
            main.install_log_forwarder(test_config)

            # Verify validation steps
            mock_validate_cli.assert_called_once()
            mock_validate_params.assert_called_once_with(test_config)
            mock_list_subs.assert_called_once()
            mock_check_fresh.assert_called_once_with(test_config, SUB_ID_TO_NAME)

            # Verify new installation path is taken
            mock_create_new.assert_called_once_with(test_config)

    def test_install_log_forwarder_existing_installation(self):
        """Test install_log_forwarder flow for existing installation"""
        test_config = get_test_config()

        existing_lfo = LfoMetadata(
            control_plane=LfoControlPlane(
                CONTROL_PLANE_SUBSCRIPTION_ID,
                CONTROL_PLANE_SUBSCRIPTION_NAME,
                CONTROL_PLANE_RESOURCE_GROUP,
                CONTROL_PLANE_REGION,
            ),
            monitored_subs={CONTROL_PLANE_SUBSCRIPTION_ID: CONTROL_PLANE_SUBSCRIPTION_NAME},
            tag_filter=RESOURCE_TAG_FILTERS,
            pii_rules=PII_SCRUBBER_RULES,
        )
        existing_lfos = {CONTROL_PLANE_ID: existing_lfo}

        with (
            mock_patch("azure_logging_install.main.validate_az_cli") as mock_validate_cli,
            mock_patch("azure_logging_install.main.validate_user_parameters") as mock_validate_params,
            mock_patch("azure_logging_install.main.list_users_subscriptions") as mock_list_subs,
            mock_patch("azure_logging_install.main.check_fresh_install") as mock_check_fresh,
            mock_patch("azure_logging_install.main.validate_singleton_lfo") as mock_validate_singleton,
            mock_patch("azure_logging_install.main.update_existing_lfo") as mock_update_existing,
            mock_patch("azure_logging_install.main.SKIP_SINGLETON_CHECK", False),
        ):
            mock_list_subs.return_value = SUB_ID_TO_NAME
            mock_check_fresh.return_value = existing_lfos

            # Execute the function
            main.install_log_forwarder(test_config)

            # Verify validation steps
            mock_validate_cli.assert_called_once()
            mock_validate_params.assert_called_once_with(test_config)
            mock_list_subs.assert_called_once()
            mock_check_fresh.assert_called_once_with(test_config, SUB_ID_TO_NAME)
            mock_validate_singleton.assert_called_once_with(test_config, existing_lfos)

            # Verify existing installation path is taken
            expected_lfo = next(iter(existing_lfos.values()))
            mock_update_existing.assert_called_once_with(test_config, expected_lfo)

    def test_install_log_forwarder_handles_exceptions(self):
        """Test install_log_forwarder handles exceptions properly"""
        test_config = get_test_config()

        with (
            mock_patch("azure_logging_install.main.validate_az_cli") as mock_validate_cli,
        ):
            # Mock validation failure
            error_message = "Azure CLI validation failed"
            mock_validate_cli.side_effect = FatalError(error_message)

            with self.assertRaises(FatalError) as context:
                main.install_log_forwarder(test_config)

            # Verify the correct exception was raised
            self.assertEqual(str(context.exception), error_message)
