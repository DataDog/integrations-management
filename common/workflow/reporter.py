# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generator

from ..requests import dd_request


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


@dataclass
class StepStatusReporter:
    status_reporter: "WorkflowReporter"
    step_id: str

    def report(
        self, metadata: dict[str, Any] | None = None, message: str | None = None
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        self.status_reporter.report(
            self.step_id,
            Status.IN_PROGRESS,
            message=message,
            metadata=metadata,
        )


@dataclass
class WorkflowReporter:
    workflow_id: str
    url: str

    def report(
        self,
        step: str,
        status: Status,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        response, response_status = dd_request(
            "POST",
            self.url,
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

        if response_status != 201:
            raise RuntimeError(f"failed to report status: {response}")

    @contextmanager
    def report_step(self, step_id: str, loading_message: str | None = None) -> Generator[StepStatusReporter, str, ]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.IN_PROGRESS)
        try:
            yield StepStatusReporter(self, step_id)
        except Exception as e:
            self.report(step_id, Status.FAILED, message=str(e))
            raise
        else:
            self.report(step_id, Status.FINISHED)
