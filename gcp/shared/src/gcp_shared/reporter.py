# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import time
from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator, Optional

from gcp_shared.gcloud import GcloudCmd, is_logged_in
from gcp_shared.requests import dd_request


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
    def __init__(self, workflow_id: str, workflow_type: str):
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type

    def report(
        self,
        step: str,
        status: Status,
        metadata: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        response, status = dd_request(
            "POST",
            f"/api/unstable/integration/gcp/workflow/{self.workflow_type}",
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

    def receive_user_selections(self) -> Optional[dict[str, Any]]:
        """Receive user selections from the Datadog workflow."""

        while True:
            response, status = dd_request(
                "GET",
                f"/api/unstable/integration/gcp/workflow/{self.workflow_type}/{self.workflow_id}",
            )

            if status == 404 or not response:
                time.sleep(1)
                continue

            json_response = json.loads(response)

            selections: dict[str, Any] = (
                json_response["data"]["attributes"]
                .get("metadata", {})
                .get("selections")
            )

            if not selections:
                time.sleep(1)
                continue

            return selections

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

    def is_valid_workflow_id(self, final_step: str) -> bool:
        """Check if the workflow ID can be used to start a new workflow."""
        response, status = dd_request(
            "GET",
            f"/api/unstable/integration/gcp/workflow/{self.workflow_type}/{self.workflow_id}",
        )

        if status == 404:
            return True

        if status != 200:
            return False

        json_response = json.loads(response)
        statuses: list[dict[str, Any]] = (
            json_response.get("data", {}).get("attributes", {}).get("statuses", [])
        )

        # If any step has failed, we do not allow re-running the workflow (except for the login step, which can be retried).
        if any(
            step.get("status", "") == "failed"
            for step in statuses
            if step.get("step", "") != "login"
        ):
            return False

        # If the workflow has already finished, we do not allow re-running it.
        if any(
            step.get("step", "") == final_step and step.get("status", "") == "finished"
            for step in statuses
        ):
            return False

        return True

    def handle_login_step(self) -> None:
        """
        Ensure that the user is logged into the GCloud Shell.
        """
        with self.report_step("login"):
            if not is_logged_in():
                raise RuntimeError("not logged in to GCloud Shell")
        print(
            "Connected! Leave this shell running and go back to the Datadog UI to continue."
        )

    def is_scopes_step_already_completed(self) -> bool:
        """
        Check if the scopes step has already been completed in the GCP workflow.
        """
        response, status = dd_request(
            "GET",
            f"/api/unstable/integration/gcp/workflow/{self.workflow_type}/{self.workflow_id}",
        )

        if status != 200 or not response:
            return False

        json_response = json.loads(response)

        statuses = json_response["data"]["attributes"].get("statuses", [])
        if any(
            step.get("step", "") == "scopes" and step.get("status", "") == "finished"
            for step in statuses
        ):
            return True

        return False
