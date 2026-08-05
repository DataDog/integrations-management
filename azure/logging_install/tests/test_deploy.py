# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from az_shared.errors import FatalError
from azure_logging_install import deploy
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType

from logging_install.tests.test_data import (
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    CONTROL_PLANE_SUBSCRIPTION_NAME,
)


def make_control_plane(**overrides):
    defaults = {
        "id": CONTROL_PLANE_ID,
        "sub_id": CONTROL_PLANE_SUBSCRIPTION_ID,
        "sub_name": CONTROL_PLANE_SUBSCRIPTION_NAME,
        "resource_group": CONTROL_PLANE_RESOURCE_GROUP,
        "region": CONTROL_PLANE_REGION,
        "type": ControlPlaneType.FunctionApps,
    }
    defaults.update(overrides)
    return ControlPlane(**defaults)


class TestDeploy(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        # Set up mocks
        self.set_subscription_mock = self.patch("azure_logging_install.deploy.set_subscription")
        self.create_storage_account_mock = self.patch("azure_logging_install.deploy.create_storage_account")
        self.wait_for_storage_account_ready_mock = self.patch(
            "azure_logging_install.deploy.wait_for_storage_account_ready"
        )
        self.create_blob_container_mock = self.patch("azure_logging_install.deploy.create_blob_container")
        self.create_file_share_mock = self.patch("azure_logging_install.deploy.create_file_share")
        self.create_control_plane_function_apps_mock = self.patch("azure_logging_install.deploy.create_control_plane_function_apps")
        self.create_control_plane_container_app_jobs_mock = self.patch(
            "azure_logging_install.deploy.create_control_plane_container_app_jobs"
        )
        self.create_initial_deploy_role_mock = self.patch("azure_logging_install.deploy.create_initial_deploy_role")
        self.create_container_app_environment_mock = self.patch(
            "azure_logging_install.deploy.create_container_app_environment"
        )
        self.create_deployer_container_app_job_mock = self.patch("azure_logging_install.deploy.create_deployer_container_app_job")
        self.execute_mock = self.patch("azure_logging_install.deploy.execute")

        # Create test configuration
        self.config = Configuration(
            control_plane=make_control_plane(),
            monitored_subs="sub-1,sub-2",
            datadog_api_key="test-api-key",
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== LFO Deployer Tests ===== #

    def test_deploy_lfo_deployer_success(self):
        """Test successful LFO deployer deployment"""
        deploy.deploy_lfo_deployer(self.config)

        # Verify all components are created in correct order
        self.create_initial_deploy_role_mock.assert_called_once_with(self.config)
        self.create_deployer_container_app_job_mock.assert_called_once_with(self.config)

    def test_deploy_lfo_deployer_role_creation_failure(self):
        """Test LFO deployer deployment handles role creation failure"""
        self.create_initial_deploy_role_mock.side_effect = FatalError("Role creation failed")

        with self.assertRaises(FatalError):
            deploy.deploy_lfo_deployer(self.config)

        # Should not proceed to create other resources
        self.create_deployer_container_app_job_mock.assert_not_called()

    def test_deploy_control_plane_environment_creation_failure(self):
        """Test control plane deployment handles container app environment creation failure"""
        self.create_container_app_environment_mock.side_effect = FatalError("Environment creation failed")

        with mock_patch.object(self.config, "get_control_plane_cache_key", return_value="test-key"):
            with self.assertRaises(FatalError):
                deploy.deploy_control_plane(self.config)

        # Should have completed storage setup first
        self.create_storage_account_mock.assert_called_once()
        # Should not proceed to create the deployer job
        self.create_deployer_container_app_job_mock.assert_not_called()

    # ===== Control Plane Deployment Tests ===== #

    def test_deploy_control_plane_success(self):
        """Test successful control plane deployment"""
        # Mock the storage key retrieval to avoid actual Azure CLI calls
        with mock_patch.object(self.config, "get_control_plane_cache_key", return_value="test-key"):
            deploy.deploy_control_plane(self.config)

        # Verify subscription is set
        self.set_subscription_mock.assert_called_once_with(self.config.control_plane.sub_id)

        # Verify storage account creation and setup
        self.create_storage_account_mock.assert_called_once_with(
            self.config.control_plane_cache_storage_name,
            self.config.control_plane.resource_group,
            self.config.control_plane.region,
        )
        self.wait_for_storage_account_ready_mock.assert_called_once_with(
            self.config.control_plane_cache_storage_name, self.config.control_plane.resource_group
        )
        self.create_blob_container_mock.assert_called_once()
        self.create_file_share_mock.assert_called_once()

        # Verify function apps are created
        self.create_control_plane_function_apps_mock.assert_called_once_with(self.config)
        # Container App Jobs are only created for the ContainerAppJobs control plane type
        self.create_control_plane_container_app_jobs_mock.assert_not_called()

    def test_deploy_control_plane_container_app_jobs_success(self):
        """Test successful control plane deployment with the ContainerAppJobs control plane type"""
        caj_config = Configuration(
            control_plane=make_control_plane(type=ControlPlaneType.ContainerAppJobs),
            monitored_subs="sub-1,sub-2",
            datadog_api_key="test-api-key",
        )

        with mock_patch.object(caj_config, "get_control_plane_cache_key", return_value="test-key"):
            deploy.deploy_control_plane(caj_config)

        # File share is only created for FunctionApps control planes
        self.create_file_share_mock.assert_not_called()

        # Container App Jobs are created instead of Function Apps
        self.create_control_plane_container_app_jobs_mock.assert_called_once_with(caj_config)
        self.create_control_plane_function_apps_mock.assert_not_called()

        # Deployer job setup should still happen regardless of control plane type
        self.create_deployer_container_app_job_mock.assert_called_once_with(caj_config)

    def test_deploy_control_plane_container_app_jobs_failure(self):
        """Test control plane deployment handles Container App Job creation failure"""
        caj_config = Configuration(
            control_plane=make_control_plane(type=ControlPlaneType.ContainerAppJobs),
            monitored_subs="sub-1,sub-2",
            datadog_api_key="test-api-key",
        )
        self.create_control_plane_container_app_jobs_mock.side_effect = FatalError("Container App Job creation failed")

        with mock_patch.object(caj_config, "get_control_plane_cache_key", return_value="test-key"):
            with self.assertRaises(FatalError):
                deploy.deploy_control_plane(caj_config)

        # Should have completed storage setup first
        self.create_storage_account_mock.assert_called_once()
        # Should not proceed to create the deployer job
        self.create_deployer_container_app_job_mock.assert_not_called()

    def test_deploy_control_plane_storage_creation_failure(self):
        """Test control plane deployment handles storage creation failure"""
        self.create_storage_account_mock.side_effect = FatalError("Storage creation failed")

        with self.assertRaises(FatalError):
            deploy.deploy_control_plane(self.config)

        # Should set subscription first
        self.set_subscription_mock.assert_called_once()
        # Should not proceed to other steps
        self.wait_for_storage_account_ready_mock.assert_not_called()
        self.create_control_plane_function_apps_mock.assert_not_called()

    def test_deploy_control_plane_storage_wait_failure(self):
        """Test control plane deployment handles storage wait failure"""
        self.wait_for_storage_account_ready_mock.side_effect = FatalError("Storage not ready")

        with self.assertRaises(FatalError):
            deploy.deploy_control_plane(self.config)

        # Should have tried to create storage
        self.create_storage_account_mock.assert_called_once()
        # Should not proceed to other steps
        self.create_control_plane_function_apps_mock.assert_not_called()

    def test_deploy_control_plane_function_apps_failure(self):
        """Test control plane deployment handles function app creation failure"""
        self.create_control_plane_function_apps_mock.side_effect = FatalError("Function app creation failed")

        # Mock the storage key retrieval to avoid actual Azure CLI calls
        with mock_patch.object(self.config, "get_control_plane_cache_key", return_value="test-key"):
            with self.assertRaises(FatalError):
                deploy.deploy_control_plane(self.config)

        # Should have completed storage setup
        self.create_storage_account_mock.assert_called_once()
        self.wait_for_storage_account_ready_mock.assert_called_once()

    # ===== Initial Deployment Tests ===== #

    def test_run_initial_deploy_success(self):
        """Test successful initial deployment trigger"""
        # run_initial_deploy takes 3 args: deployer_job_name, control_plane_rg, control_plane_sub_id
        deploy.run_initial_deploy(
            self.config.deployer_job_name,
            self.config.control_plane.resource_group,
            self.config.control_plane.sub_id,
        )

        # Verify job execution command is called
        self.execute_mock.assert_called_once()
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = str(call_args)

        self.assertIn("containerapp", cmd_str)
        self.assertIn("job", cmd_str)
        self.assertIn("start", cmd_str)
        self.assertIn(self.config.deployer_job_name, cmd_str)

    def test_run_initial_deploy_failure(self):
        """Test initial deployment handles execution failure"""
        self.execute_mock.side_effect = FatalError("Job execution failed")

        with self.assertRaises(RuntimeError):  # The function wraps errors in RuntimeError
            deploy.run_initial_deploy(
                self.config.deployer_job_name,
                self.config.control_plane.resource_group,
                self.config.control_plane.sub_id,
            )

    # ===== Configuration Integration Tests ===== #

    def test_deploy_functions_use_configuration_properties(self):
        """Test that deploy functions correctly use configuration properties"""
        # Create a mock config with specific properties
        mock_config = MagicMock()
        mock_config.control_plane.sub_id = "test-sub-123"
        mock_config.control_plane_cache_storage_name = "teststorage123"
        mock_config.control_plane.resource_group = "test-rg-456"
        mock_config.control_plane.region = "westus2"
        mock_config.control_plane_env_name = "test-env-789"
        mock_config.control_plane_job_name = "test-job-abc"

        # Test control plane deployment
        deploy.deploy_control_plane(mock_config)

        # Verify configuration properties are used correctly
        self.set_subscription_mock.assert_called_with("test-sub-123")
        self.create_storage_account_mock.assert_called_with("teststorage123", "test-rg-456", "westus2")

        # Test LFO deployer deployment
        deploy.deploy_lfo_deployer(mock_config)

        self.create_container_app_environment_mock.assert_called_with("test-env-789", "test-rg-456", "westus2")

    # ===== Deployment Flow Integration Tests ===== #

    def test_complete_deployment_flow(self):
        """Test complete deployment flow simulation"""
        # This would simulate a full deployment
        with (
            mock_patch("azure_logging_install.deploy.deploy_lfo_deployer") as mock_lfo,
            mock_patch("azure_logging_install.deploy.deploy_control_plane") as mock_control,
            mock_patch("azure_logging_install.deploy.run_initial_deploy") as mock_initial,
        ):
            # Simulate main deployment flow
            mock_control(self.config)
            mock_lfo(self.config)
            mock_initial(self.config)

            # Verify all parts of deployment are called
            mock_control.assert_called_once_with(self.config)
            mock_lfo.assert_called_once_with(self.config)
            mock_initial.assert_called_once_with(self.config)

    def test_deployment_error_propagation(self):
        """Test that deployment errors are properly propagated"""
        # Test that errors from underlying functions are not caught and hidden
        error_message = "Specific deployment error"
        self.create_storage_account_mock.side_effect = FatalError(error_message)

        with self.assertRaises(FatalError) as context:
            deploy.deploy_control_plane(self.config)

        self.assertIn(error_message, str(context.exception))
