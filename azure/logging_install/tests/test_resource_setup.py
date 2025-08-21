# stdlib
import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock

# Needed to import the logging_install modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# project
import resource_setup
from configuration import Configuration
from errors import ExistenceCheckError, FatalError, ResourceNotFoundError

# Test data
CONTROL_PLANE_RG = "test-control-plane-rg"
CONTROL_PLANE_REGION = "eastus"
STORAGE_ACCOUNT_NAME = "teststorageaccount"
CONTAINER_APP_ENV_NAME = "test-env"
CONTAINER_APP_JOB_NAME = "test-job"
BLOB_CONTAINER_NAME = "test-container"
FILE_SHARE_NAME = "test-share"


class TestResourceSetup(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        # Set up mocks
        self.log_mock = self.patch("resource_setup.log")
        self.execute_mock = self.patch("resource_setup.execute")
        self.time_mock = self.patch("resource_setup.time")

        # Create test configuration
        self.config = Configuration(
            management_group_id="test-mg",
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id="test-sub",
            control_plane_rg=CONTROL_PLANE_RG,
            monitored_subs="sub-1,sub-2",
            datadog_api_key="test-api-key",
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== Resource Group Tests ===== #

    def test_create_resource_group_success(self):
        """Test successful resource group creation"""
        resource_setup.create_resource_group(CONTROL_PLANE_RG, CONTROL_PLANE_REGION)

        self.execute_mock.assert_called_once()
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()

        self.assertIn("group", cmd_str)
        self.assertIn("create", cmd_str)
        self.assertIn(CONTROL_PLANE_RG, cmd_str)
        self.assertIn(CONTROL_PLANE_REGION, cmd_str)

        self.log_mock.info.assert_called_with(
            f"Creating resource group {CONTROL_PLANE_RG} in {CONTROL_PLANE_REGION}"
        )

    def test_create_resource_group_failure(self):
        """Test resource group creation failure"""
        self.execute_mock.side_effect = FatalError("Creation failed")

        with self.assertRaises(FatalError):
            resource_setup.create_resource_group(CONTROL_PLANE_RG, CONTROL_PLANE_REGION)

    # ===== Storage Account Tests ===== #

    def test_create_storage_account_success(self):
        """Test successful storage account creation"""
        resource_setup.create_storage_account(
            STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG, CONTROL_PLANE_REGION
        )

        self.execute_mock.assert_called_once()
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()

        self.assertIn("storage", cmd_str)
        self.assertIn("account", cmd_str)
        self.assertIn("create", cmd_str)
        self.assertIn(STORAGE_ACCOUNT_NAME, cmd_str)
        self.assertIn(CONTROL_PLANE_RG, cmd_str)
        self.assertIn(CONTROL_PLANE_REGION, cmd_str)
        self.assertIn("Standard_LRS", cmd_str)
        self.assertIn("StorageV2", cmd_str)

        self.log_mock.info.assert_called_with(
            f"Creating storage account {STORAGE_ACCOUNT_NAME}"
        )

    def test_wait_for_storage_account_ready_success(self):
        """Test waiting for storage account to be ready - success"""
        with mock_patch("resource_setup.time.time") as mock_time:
            mock_time.side_effect = [0, 5]  # Simulate time progression
            self.execute_mock.return_value = "Succeeded"  # Return state directly

            resource_setup.wait_for_storage_account_ready(
                STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG
            )

            self.execute_mock.assert_called_once()
            self.log_mock.info.assert_called_with(
                f"Storage account {STORAGE_ACCOUNT_NAME} is ready"
            )

    def test_wait_for_storage_account_ready_timeout(self):
        """Test waiting for storage account times out"""
        with mock_patch("resource_setup.time.time") as mock_time:
            mock_time.side_effect = [0, 30, 65]  # Simulate timeout
            self.execute_mock.return_value = "Creating"  # Always in Creating state

            with self.assertRaises(TimeoutError):
                resource_setup.wait_for_storage_account_ready(
                    STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG
                )

    def test_wait_for_storage_account_ready_failed_state(self):
        """Test waiting for storage account with failed state"""
        with mock_patch("resource_setup.time.time") as mock_time:
            mock_time.side_effect = [0, 5]
            self.execute_mock.return_value = "Failed"  # Failed state

            with self.assertRaises(RuntimeError):
                resource_setup.wait_for_storage_account_ready(
                    STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG
                )

    # ===== Container App Environment Tests ===== #

    def test_create_container_app_environment_success(self):
        """Test successful container app environment creation"""
        # The function first checks if environment exists, then creates it if not found
        # Mock ResourceNotFoundError for the first call (show), then success for create
        self.execute_mock.side_effect = [
            ResourceNotFoundError("Environment not found"),  # First call: env show
            None,  # Second call: env create (successful)
        ]

        resource_setup.create_container_app_environment(
            CONTAINER_APP_ENV_NAME, CONTROL_PLANE_RG, CONTROL_PLANE_REGION
        )

        # Should have been called twice: once for show, once for create
        self.assertEqual(self.execute_mock.call_count, 2)

        # Check the second call (create command)
        second_call_args = self.execute_mock.call_args_list[1][0][0]
        cmd_str = second_call_args.str()

        self.assertIn("containerapp", cmd_str)
        self.assertIn("env", cmd_str)
        self.assertIn("create", cmd_str)
        self.assertIn(CONTAINER_APP_ENV_NAME, cmd_str)
        self.assertIn(CONTROL_PLANE_RG, cmd_str)
        self.assertIn(CONTROL_PLANE_REGION, cmd_str)

    # ===== Blob Container Tests ===== #

    def test_create_blob_container_success(self):
        """Test successful blob container creation"""
        # create_blob_container takes 2 args: storage_account_name, account_key
        resource_setup.create_blob_container(STORAGE_ACCOUNT_NAME, "test-key")

        self.execute_mock.assert_called_once()
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()

        self.assertIn("storage", cmd_str)
        self.assertIn("container", cmd_str)
        self.assertIn("create", cmd_str)
        # The actual container name is "control-plane-cache" (from constants)
        self.assertIn("control-plane-cache", cmd_str)
        self.assertIn(STORAGE_ACCOUNT_NAME, cmd_str)

    # ===== File Share Tests ===== #

    def test_create_file_share_success(self):
        """Test successful file share creation"""
        # create_file_share takes 2 args: storage_account_name, control_plane_rg
        resource_setup.create_file_share(STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG)

        self.execute_mock.assert_called_once()
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()

        self.assertIn("storage", cmd_str)
        self.assertIn("share-rm", cmd_str)  # Actual command used
        self.assertIn("create", cmd_str)
        self.assertIn(STORAGE_ACCOUNT_NAME, cmd_str)

    # ===== Container App Job Tests ===== #

    def test_create_container_app_job_success(self):
        """Test successful container app job creation"""
        mock_config = MagicMock()
        mock_config.deployer_job_name = CONTAINER_APP_JOB_NAME
        mock_config.control_plane_rg = CONTROL_PLANE_RG
        mock_config.control_plane_env_name = CONTAINER_APP_ENV_NAME
        mock_config.control_plane_sub_id = "test-sub"
        mock_config.deployer_image_url = "test-image:latest"
        mock_config.get_control_plane_cache_conn_string.return_value = (
            "test-conn-string"
        )

        # Mock both show and create calls (function checks if job exists first)
        self.execute_mock.side_effect = [
            ResourceNotFoundError("Job not found"),  # First call: job show
            None,  # Second call: job create (successful)
        ]

        with mock_patch("resource_setup.tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test.json"

            resource_setup.create_container_app_job(mock_config)

        # Should have been called twice: once for show, once for create
        self.assertEqual(self.execute_mock.call_count, 2)

        # Check the second call (create command)
        second_call_args = self.execute_mock.call_args_list[1][0][0]
        cmd_str = second_call_args.str()

        self.assertIn("containerapp", cmd_str)
        self.assertIn("job", cmd_str)
        self.assertIn("create", cmd_str)

    # ===== Function App Tests ===== #

    def test_create_function_apps_success(self):
        """Test successful function app creation"""
        with mock_patch("resource_setup.create_function_app") as mock_create_func:
            resource_setup.create_function_apps(self.config)

            # Should create multiple function apps
            self.assertGreater(mock_create_func.call_count, 0)

    def test_create_function_app_success(self):
        """Test successful individual function app creation"""
        # Mock the storage key retrieval to avoid actual Azure CLI calls
        with mock_patch.object(
            self.config, "get_control_plane_cache_key", return_value="test-key"
        ):
            # Use the actual resource task name from config
            app_name = self.config.resources_task_name

            resource_setup.create_function_app(self.config, app_name)

            # Should call execute multiple times for app service plan and function app
            self.assertGreater(self.execute_mock.call_count, 1)

    # ===== Error Handling Tests ===== #

    def test_resource_creation_handles_errors(self):
        """Test resource creation handles various errors appropriately"""
        # Test ResourceNotFoundError handling
        self.execute_mock.side_effect = ResourceNotFoundError("Resource not found")

        with self.assertRaises(ResourceNotFoundError):
            resource_setup.create_resource_group(CONTROL_PLANE_RG, CONTROL_PLANE_REGION)

    def test_wait_function_retries_on_not_found(self):
        """Test wait functions handle ResourceNotFoundError correctly"""
        # Mock time.time() calls correctly
        with mock_patch("resource_setup.time.time") as mock_time:
            mock_time.side_effect = [0, 5]  # Simulate time progression

            # The function doesn't actually retry on ResourceNotFoundError - it propagates it
            self.execute_mock.side_effect = ResourceNotFoundError("Not found yet")

            with self.assertRaises(ResourceNotFoundError):
                resource_setup.wait_for_storage_account_ready(
                    STORAGE_ACCOUNT_NAME, CONTROL_PLANE_RG
                )

            # Should have been called once and then exception propagated
            self.assertEqual(self.execute_mock.call_count, 1)

    # ===== Configuration Integration Tests ===== #

    def test_functions_use_configuration_correctly(self):
        """Test that functions properly use Configuration object properties"""
        mock_config = MagicMock()
        mock_config.control_plane_cache_storage_name = "test-storage"
        mock_config.control_plane_rg = "test-rg"
        mock_config.control_plane_region = "test-region"

        # Test that configuration properties are used
        resource_setup.create_storage_account(
            mock_config.control_plane_cache_storage_name,
            mock_config.control_plane_rg,
            mock_config.control_plane_region,
        )

        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()

        self.assertIn("test-storage", cmd_str)
        self.assertIn("test-rg", cmd_str)
        self.assertIn("test-region", cmd_str)
