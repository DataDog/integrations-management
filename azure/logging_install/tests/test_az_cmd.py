# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import Mock

from azure_logging_install.az_cmd import AzCmd, set_subscription

from shared.tests.test_data import (
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
    CONTROL_PLANE_SUBSCRIPTION_ID,
)
from shared.tests.test_execute_cmd import CmdExecutionTestCase


class TestAzCmd(TestCase):
    def test_az_cmd_initialization(self):
        """Test AzCmd builder initialization"""
        cmd = AzCmd("functionapp", "create")

        self.assertEqual(list(cmd), ["functionapp", "create"])

    def test_az_cmd_initialization_with_multi_word_action(self):
        """Test AzCmd builder with multi-word action"""
        cmd = AzCmd("storage", "account create")

        self.assertEqual(list(cmd), ["storage", "account", "create"])

    def test_az_cmd_param(self):
        """Test adding key-value parameters"""
        cmd = AzCmd("functionapp", "create")
        result = cmd.param("--resource-group", CONTROL_PLANE_RESOURCE_GROUP)

        self.assertIs(result, cmd)
        self.assertEqual(
            list(cmd),
            ["functionapp", "create", "--resource-group", CONTROL_PLANE_RESOURCE_GROUP],
        )

    def test_az_cmd_param_list(self):
        """Test adding list parameters"""
        cmd = AzCmd("functionapp", "create")
        values = ["value1", "value2", "value3"]
        result = cmd.param_list("--tags", values)

        self.assertIs(result, cmd)
        expected = [
            "functionapp",
            "create",
            "--tags",
            "value1",
            "value2",
            "value3",
        ]
        self.assertEqual(list(cmd), expected)

    def test_az_cmd_flag(self):
        """Test adding flags"""
        cmd = AzCmd("functionapp", "create")
        result = cmd.flag("--yes")

        self.assertIs(result, cmd)
        self.assertEqual(list(cmd), ["functionapp", "create", "--yes"])

    def test_az_cmd_chaining(self):
        """Test method chaining"""
        cmd = (
            AzCmd("functionapp", "create")
            .param("--resource-group", CONTROL_PLANE_RESOURCE_GROUP)
            .param("--location", CONTROL_PLANE_REGION)
            .flag("--yes")
        )

        expected = [
            "functionapp",
            "create",
            "--resource-group",
            CONTROL_PLANE_RESOURCE_GROUP,
            "--location",
            CONTROL_PLANE_REGION,
            "--yes",
        ]
        self.assertEqual(list(cmd), expected)

    def test_az_cmd_str(self):
        """Test string representation of command"""
        cmd = AzCmd("functionapp", "create").param("--resource-group", CONTROL_PLANE_RESOURCE_GROUP).flag("--yes")

        expected = f"az {'functionapp'} create --resource-group {CONTROL_PLANE_RESOURCE_GROUP} --yes"
        self.assertEqual(str(cmd), expected)


class TestCommands(CmdExecutionTestCase):
    def test_set_subscription_success(self):
        """Test successful subscription setting"""
        mock_result = Mock()
        mock_result.stdout = "Subscription set"
        mock_result.returncode = 0
        self.subprocess_mock.return_value = mock_result

        set_subscription(CONTROL_PLANE_SUBSCRIPTION_ID)

        # Verify the correct command was called
        call_args = self.subprocess_mock.call_args
        cmd_list = call_args[0][0]
        self.assertIn("account", cmd_list)
        self.assertIn("set", cmd_list)
        self.assertIn("--subscription", cmd_list)
        self.assertIn(CONTROL_PLANE_SUBSCRIPTION_ID, cmd_list)

    def test_set_subscription_with_error(self):
        """Test set_subscription handles errors"""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = "Subscription not found"
        mock_result.returncode = 1
        self.subprocess_mock.return_value = mock_result

        with self.assertRaises(RuntimeError):
            set_subscription(CONTROL_PLANE_SUBSCRIPTION_ID)
