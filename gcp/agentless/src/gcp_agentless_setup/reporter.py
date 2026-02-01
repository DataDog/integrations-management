# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Composite reporter that outputs to console and Datadog workflow status API."""

from enum import Enum
from typing import Any, NoReturn, Optional

from gcp_shared.reporter import WorkflowReporter, Status

from .console_reporter import ConsoleReporter, Step
from .errors import SetupError


WORKFLOW_TYPE = "gcp-agentless-setup"


class AgentlessStep(str, Enum):
    """Step identifiers for the agentless setup workflow."""

    LOGIN = "login"
    PREFLIGHT_CHECKS = "preflight_checks"
    CREATE_STATE_BUCKET = "create_state_bucket"
    STORE_API_KEY = "store_api_key"
    GENERATE_TERRAFORM_CONFIG = "generate_terraform_config"
    TERRAFORM_INIT = "terraform_init"
    DEPLOY_INFRASTRUCTURE = "deploy_infrastructure"


# The final step that marks the workflow as complete
FINAL_STEP = AgentlessStep.DEPLOY_INFRASTRUCTURE


class Reporter:
    """Composite reporter that outputs to console and Datadog workflow status API.
    
    This class combines console output (for user feedback in the terminal) with
    API reporting (for the Datadog UI to track progress). It delegates to:
    - ConsoleReporter: Handles formatted stdout/stderr output
    - WorkflowReporter: Handles Datadog workflow status API communication
    
    Args:
        total_steps: Total number of steps in the setup process.
        workflow_id: The workflow ID for API reporting (required).
    """

    def __init__(self, total_steps: int, workflow_id: str):
        self._current_step_id: Optional[AgentlessStep] = None

        self.console = ConsoleReporter(total_steps=total_steps)
        # Initialize workflow reporter for API communication
        self.workflow = WorkflowReporter(
            workflow_id=workflow_id,
            workflow_type=WORKFLOW_TYPE,
        )

    def handle_login_step(self) -> None:
        """Handle the login step - verify GCloud auth and report to API.

        This delegates to the shared WorkflowReporter which handles
        authentication verification and status reporting.
        """
        self.workflow.handle_login_step()

    def is_valid_workflow_id(self) -> bool:
        """Check if the workflow ID can be used to start a new workflow."""
        return self.workflow.is_valid_workflow_id(FINAL_STEP.value)

    def start_step(self, name: str, step_id: AgentlessStep) -> Step:
        """Start a new step.

        Args:
            name: Human-readable step name for console output.
            step_id: Step identifier for API reporting.
        
        Returns:
            Step object with metadata.
        """
        self._current_step_id = step_id

        step = self.console.start_step(name, step_id.value)

        self.workflow.report(
            step=step_id.value,
            status=Status.IN_PROGRESS,
        )

        return step

    def finish_step(self, metadata: Optional[dict[str, Any]] = None) -> None:
        """Mark current step as finished.

        Args:
            metadata: Optional metadata to include in the status report.
        """
        self.console.finish_step()
        if self._current_step_id:
            self.workflow.report(
                step=self._current_step_id.value,
                status=Status.FINISHED,
                metadata=metadata,
            )

    def success(self, message: str) -> None:
        """Report success message for current step."""
        self.console.success(message)

    def info(self, message: str) -> None:
        """Report info message."""
        self.console.info(message)

    def warning(self, message: str) -> None:
        """Report warning message."""
        self.console.warning(message)

    def error(self, message: str, detail: Optional[str] = None) -> None:
        """Report error message.

        Args:
            message: Error message.
            detail: Optional detailed error information.
        """
        self.console.error(message, detail)
        if self._current_step_id:
            self.workflow.report(
                step=self._current_step_id.value,
                status=Status.FAILED,
                message=message,
            )

    def fatal(self, message: str, detail: Optional[str] = None) -> NoReturn:
        """Report fatal error and raise exception."""
        self.error(message, detail)
        raise SetupError(message, detail)

    def complete(self) -> None:
        """Report setup complete."""
        self.console.complete()

    def summary(self, scanner_project: str, regions: list[str], projects: list[str]) -> None:
        """Print deployment summary."""
        self.console.summary(scanner_project, regions, projects)
