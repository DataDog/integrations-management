# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Composite reporter that outputs to console and Datadog workflow status API."""

import json
from enum import Enum
from typing import Any, NoReturn, Optional

from .console_reporter import ConsoleReporter, Step
from .errors import SetupError
from .requests import dd_request
from .shell import az_cli


WORKFLOW_TYPE = "azure-agentless-setup"


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class AgentlessStep(str, Enum):
    """Step identifiers for the Azure agentless setup workflow."""

    LOGIN = "login"
    PREFLIGHT_CHECKS = "preflight_checks"
    CREATE_STATE_STORAGE = "create_state_storage"
    STORE_API_KEY = "store_api_key"
    GENERATE_TERRAFORM_CONFIG = "generate_terraform_config"
    TERRAFORM_INIT = "terraform_init"
    DEPLOY_INFRASTRUCTURE = "deploy_infrastructure"


FINAL_STEP = AgentlessStep.DEPLOY_INFRASTRUCTURE


class Reporter:
    """Composite reporter: console output + Datadog workflow status API.

    Args:
        total_steps: Total number of steps in the setup process.
        workflow_id: The workflow ID for API reporting.
    """

    def __init__(self, total_steps: int, workflow_id: str):
        self._current_step_id: Optional[AgentlessStep] = None

        self.console = ConsoleReporter(total_steps=total_steps)
        self.workflow_id = workflow_id

    def _report_to_api(
        self,
        step: str,
        status: Status,
        metadata: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        """Report step status to the Datadog workflow status API."""
        try:
            dd_request(
                "POST",
                f"/api/unstable/integration/azure/workflow/{WORKFLOW_TYPE}",
                {
                    "data": {
                        "id": self.workflow_id,
                        "type": "integration_setup_status",
                        "attributes": {
                            "status": status.value,
                            "step": step,
                            "metadata": metadata,
                            "message": message,
                        },
                    }
                },
            )
        except Exception:
            # Don't let API reporting failures block the setup
            pass

    def handle_login_step(self) -> None:
        """Verify Azure CLI authentication and report to the workflow API."""
        self._report_to_api("login", Status.IN_PROGRESS)
        try:
            success, result = az_cli(["account", "show"])
            if not success:
                raise RuntimeError("not logged in to Azure CLI")
        except Exception as e:
            self._report_to_api("login", Status.FAILED, message=str(e))
            if "az: command not found" in str(e) or "'az' is not recognized" in str(e):
                print(
                    "You must install the Azure CLI and log in to run this script.\n"
                    "https://learn.microsoft.com/cli/azure/install-azure-cli"
                )
            else:
                print("You must be logged in to Azure CLI to run this script.")
                print("Run: az login")
            exit(1)
        else:
            self._report_to_api("login", Status.FINISHED)

    def is_valid_workflow_id(self) -> bool:
        """Check if the workflow ID can be used to start a new workflow."""
        try:
            response, status = dd_request(
                "GET",
                f"/api/unstable/integration/azure/workflow/{WORKFLOW_TYPE}/{self.workflow_id}",
            )
        except Exception:
            return True

        if status == 404:
            return True

        if status != 200:
            return False

        json_response = json.loads(response)
        statuses: list[dict[str, Any]] = (
            json_response.get("data", {}).get("attributes", {}).get("statuses", [])
        )

        if any(
            step.get("status", "") == "failed"
            for step in statuses
            if step.get("step", "") != "login"
        ):
            return False

        if any(
            step.get("step", "") == FINAL_STEP.value and step.get("status", "") == "finished"
            for step in statuses
        ):
            return False

        return True

    def start_step(self, name: str, step_id: AgentlessStep) -> Step:
        self._current_step_id = step_id
        step = self.console.start_step(name, step_id.value)
        self._report_to_api(step=step_id.value, status=Status.IN_PROGRESS)
        return step

    def finish_step(self, metadata: Optional[dict[str, Any]] = None) -> None:
        self.console.finish_step()
        if self._current_step_id:
            self._report_to_api(
                step=self._current_step_id.value,
                status=Status.FINISHED,
                metadata=metadata,
            )

    def success(self, message: str) -> None:
        self.console.success(message)

    def info(self, message: str) -> None:
        self.console.info(message)

    def warning(self, message: str) -> None:
        self.console.warning(message)

    def error(self, message: str, detail: Optional[str] = None) -> None:
        self.console.error(message, detail)
        if self._current_step_id:
            self._report_to_api(
                step=self._current_step_id.value,
                status=Status.FAILED,
                message=message,
            )

    def fatal(self, message: str, detail: Optional[str] = None) -> NoReturn:
        self.error(message, detail)
        raise SetupError(message, detail)

    def complete(self) -> None:
        self.console.complete()

    def summary(self, scanner_subscription: str, locations: list[str], subscriptions: list[str]) -> None:
        self.console.summary(scanner_subscription, locations, subscriptions)
