# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator, Optional


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class StepStatusReporter:
    def __init__(self, status_reporter: "WorkflowReporter", step_id: str):
        self.status_reporter = status_reporter
        self.step_id = step_id

    def report(
        self, metadata: Optional[dict[str, Any]] = None, message: Optional[str] = None
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        self.status_reporter.report(
            self.step_id,
            Status.IN_PROGRESS,
            message=message,
            metadata=metadata,
        )


class WorkflowReporter:
    def __init__(self, workflow_id: str, dd_request_func):
        self.workflow_id = workflow_id
        self.dd_request = dd_request_func

    def report(
        self,
        step: str,
        status: Status,
        metadata: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        response, status = self.dd_request(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
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

        if status != 201:
            raise RuntimeError(f"failed to report status: {response}")

    @contextmanager
    def report_step(self, step_id: str) -> Generator[StepStatusReporter, str, None]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.IN_PROGRESS)
        try:
            yield StepStatusReporter(self, step_id)
        except Exception as e:
            self.report(
                step_id,
                Status.FAILED,
                message=str(e),
            )
            raise
        else:
            self.report(step_id, Status.FINISHED)
