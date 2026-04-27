# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Composite reporter that outputs to console and Datadog workflow status API."""

from enum import Enum
from typing import Any, NoReturn, Optional

from az_shared.script_status import Status, StatusReporter

from .console_reporter import ConsoleReporter, Step
from .errors import SetupError


WORKFLOW_TYPE = "azure-agentless-setup"


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

    Wraps the shared ``az_shared.script_status.StatusReporter`` (API transport)
    and ``ConsoleReporter`` (terminal UX). The agentless flow uses imperative
    ``start_step`` / ``finish_step`` boundaries (steps cross function calls,
    e.g. into the Terraform runner), so it calls ``StatusReporter.report``
    directly rather than using the ``report_step`` context manager.

    Args:
        total_steps: Total number of steps in the setup process.
        workflow_id: Workflow ID for API reporting.
    """

    def __init__(self, total_steps: int, workflow_id: str):
        self._current_step_id: Optional[AgentlessStep] = None

        self.console = ConsoleReporter(total_steps=total_steps)
        self.status = StatusReporter(workflow_type=WORKFLOW_TYPE, workflow_id=workflow_id)

    def handle_login_step(self) -> None:
        """Verify Azure CLI auth and report the login step to the workflow API."""
        self.status.handle_login_step()

    def is_valid_workflow_id(self) -> bool:
        """Return True if the workflow ID can be used to start a new workflow."""
        return self.status.is_valid_workflow_id(FINAL_STEP.value)

    def start_step(self, name: str, step_id: AgentlessStep) -> Step:
        self._current_step_id = step_id
        step = self.console.start_step(name, step_id.value)
        self.status.report(
            step_id.value,
            Status.IN_PROGRESS,
            f"{step_id.value}: {Status.IN_PROGRESS}",
        )
        return step

    def finish_step(self, metadata: Optional[dict[str, Any]] = None) -> None:
        self.console.finish_step()
        if self._current_step_id:
            self.status.report(
                self._current_step_id.value,
                Status.FINISHED,
                f"{self._current_step_id.value}: {Status.FINISHED}",
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
            self.status.report(
                self._current_step_id.value,
                Status.FAILED,
                message,
            )

    def fatal(self, message: str, detail: Optional[str] = None) -> NoReturn:
        self.error(message, detail)
        raise SetupError(message, detail)

    def complete(self) -> None:
        self.console.complete()

    def summary(
        self,
        scanner_subscription: str,
        locations: list[str],
        subscriptions: list[str],
    ) -> None:
        self.console.summary(scanner_subscription, locations, subscriptions)
