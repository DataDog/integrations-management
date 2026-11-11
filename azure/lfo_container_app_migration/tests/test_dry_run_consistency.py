# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Checks that --dry-run output can't drift from what the migration actually does.

Each step's real execute() runs against a fake Azure CLI that records commands instead of running them.
Every change it would make (each create/update/delete/stop/start) must be named in that step's describe(),
and describe() itself must not make any changes.
"""

import json
import re
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceGroupNotFoundError, ResourceNotFoundError
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import ROLE_NAMES, STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS

from azure_lfo_container_app_migration.migration import _build_caj_config, _build_cleanup_steps, _build_migration_steps

CONTROL_PLANE_SUB = "cp-sub"
SUB_WITH_RG = "sub-1"
SUB_WITHOUT_RG = "sub-2"
RESOURCE_GROUP = "lfo-rg"

# Every module that imports `execute` by name on the migration's code paths
EXECUTE_IMPORTERS = [
    "az_shared.auth",
    "azure_logging_install.configuration",
    "azure_logging_install.resource_setup",
    "azure_logging_install.role_setup",
    "azure_lfo_container_app_migration.grant_permissions",
]
MUTATING_ACTIONS = {"create", "update", "delete", "stop", "start"}


class FakeAzureCli:
    """Stands in for az_shared.execute_cmd.execute: records commands and answers read-only ones."""

    def __init__(self):
        self.mutations: list[tuple[tuple[str, ...], dict[str, str], str]] = []
        self.active_sub = CONTROL_PLANE_SUB

    def __call__(self, cmd, can_fail: bool = False) -> str:
        tokens = [t for t in cmd if t != "az"]
        first_flag = next((i for i, t in enumerate(tokens) if t.startswith("--")), len(tokens))
        action = tuple(tokens[:first_flag])
        params = {
            tokens[i]: tokens[i + 1] if i + 1 < len(tokens) and not tokens[i + 1].startswith("--") else ""
            for i in range(first_flag, len(tokens))
            if tokens[i].startswith("--")
        }

        if action == ("account", "set"):
            self.active_sub = params["--subscription"]
            return ""
        if action[-1] in MUTATING_ACTIONS:
            self.mutations.append((action, params, self.active_sub))
            return ""
        return self._read(action, params)

    def _read(self, action: tuple[str, ...], params: dict[str, str]) -> str:
        if action == ("containerapp", "job", "show"):
            if "--query" in params:
                return f"principal:{params['--name']}"
            raise ResourceNotFoundError("job not found")  # the new jobs don't exist yet
        if action == ("group", "show"):
            if params["--subscription"] == SUB_WITHOUT_RG:
                raise ResourceGroupNotFoundError("resource group not found")
            return "{}"
        if action == ("group", "exists"):
            return "false" if params["--subscription"] == SUB_WITHOUT_RG else "true"
        if action == ("role", "assignment", "list"):
            if params.get("--query") == "[].id":
                return f"assignment:{params['--role']}"
            return "0"
        if action == ("storage", "account", "keys", "list"):
            return json.dumps([{"permissions": STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS, "value": "storage-key"}])
        if action == ("functionapp", "show"):
            return "/subscriptions/cp-sub/resourceGroups/lfo-rg/providers/Microsoft.Web/serverfarms/plan"
        return ""


def described_role_assignments(description: str) -> set[tuple[str, str, str]]:
    """Parses (subscription, identity name, role name) out of a describe() role assignment listing."""
    assignments = set()
    current_sub = None
    for line in description.splitlines():
        if sub := re.search(r"Subscription ([^\s:]+)", line):
            current_sub = sub.group(1)
        if match := re.search(r"'([^']+)': (.+?) on ", line):
            sub = re.search(r"in subscription (\S+)", line)
            assignments.add((sub.group(1) if sub else current_sub, match.group(1), match.group(2)))
    return assignments


class TestDryRunMatchesExecution(TestCase):
    def setUp(self) -> None:
        self.fake_az = FakeAzureCli()
        for module in EXECUTE_IMPORTERS:
            patcher = mock_patch(f"{module}.execute", side_effect=self.fake_az)
            self.addCleanup(patcher.stop)
            patcher.start()

        function_app_config = Configuration(
            control_plane=ControlPlane(
                id="abcdef123456",
                sub_id=CONTROL_PLANE_SUB,
                resource_group=RESOURCE_GROUP,
                region="eastus",
                type=ControlPlaneType.FunctionApps,
            ),
            monitored_subs=f"{SUB_WITH_RG},{SUB_WITHOUT_RG}",
            datadog_api_key="test-api-key",
        )
        caj_config = _build_caj_config(function_app_config)
        self.steps = _build_migration_steps(caj_config, function_app_config) + _build_cleanup_steps(
            caj_config, function_app_config
        )

    def test_every_change_a_step_makes_is_in_its_description(self):
        for step in self.steps:
            with self.subTest(step=step.name):
                self.fake_az.mutations.clear()
                description = step.describe()
                self.assertEqual(self.fake_az.mutations, [], "describe() must not change anything")

                step.execute()

                self.assertNotEqual(self.fake_az.mutations, [], "expected execute() to make changes")
                for action, params, active_sub in self.fake_az.mutations:
                    self._assert_described(description, action, params, active_sub)

    def _assert_described(self, description: str, action: tuple[str, ...], params: dict[str, str], active_sub: str):
        command = " ".join(action)
        if action == ("role", "assignment", "create"):
            sub_id = re.match(r"/subscriptions/([^/]+)", params["--scope"]).group(1)
            identity = params["--assignee-object-id"].removeprefix("principal:")
            expected = (sub_id, identity, ROLE_NAMES[params["--role"]])
            self.assertIn(expected, described_role_assignments(description), f"{command} {expected} not described")
        elif action == ("role", "assignment", "delete"):
            role_id = params["--ids"].removeprefix("assignment:")
            self.assertIn(ROLE_NAMES[role_id], description, f"{command} of {role_id} not described")
        elif action == ("group", "create"):
            line = next((line for line in description.splitlines() if f"Subscription {active_sub}" in line), "")
            self.assertIn(f"'{params['--name']}' does not exist, would be created", line)
        elif action == ("functionapp", "plan", "delete"):
            self.assertIn("App Service plan", description)
        else:
            self.assertIn("--name", params, f"no rule to check that '{command}' is described")
            self.assertIn(params["--name"], description, f"{command} of '{params['--name']}' not described")
