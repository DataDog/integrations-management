# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Optional
from urllib.error import HTTPError

from az_shared.errors import UserActionRequiredError, UserRetriableError
from azure_integration_quickstart.util import Json, dd_request


class Status(Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"
    WARN = "warn"
    USER_ACTIONABLE_ERROR = "USER_ACTIONABLE_ERROR"
    FAILING_AWAITING_USER_DECISION = "failing_awaiting_user_decision"


@dataclass
class StatusReporter:
    EXPIRED_TOKEN_ERROR = "Lifetime validation failed, the token is expired"
    USER_DECISION_TIMEOUT_SECONDS = 60

    workflow_type: str
    workflow_id: str

    def report(self, step_id: str, status: Status, message: Optional[str], metadata: Optional[Json] = None) -> None:
        """Report the status of a step in a workflow to Datadog."""
        dd_request(
            "POST",
            f"/api/unstable/integration/azure/workflow/{self.workflow_type}",
            {
                "data": {
                    "id": self.workflow_id,
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": status.value,
                        "step": step_id,
                        "message": message,
                        "metadata": metadata,
                    },
                }
            },
        )

    def _poll_for_user_decision(self) -> Optional[bool]:
        """Poll GetWorkflowIdStatuses every 1s until user_error_decision step appears or timeout.

        Returns True if user approved log forwarding, False if declined or dismissed, None on timeout.
        """
        deadline = time.time() + self.USER_DECISION_TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                status_response, _ = dd_request(
                    "GET",
                    f"/api/unstable/integration/azure/workflow/{self.workflow_type}/{self.workflow_id}",
                )
            except HTTPError as e:
                if e.code == 404:
                    time.sleep(1)
                    continue
                else:
                    raise RuntimeError("Error retrieving user decision from Datadog") from e
            json_status_response = json.loads(status_response)
            statuses = json_status_response["data"]["attributes"].get("statuses", [])
            if any(s["step"] == "user_error_decision" and s["status"] == "finished" for s in statuses):
                return bool(
                    json_status_response["data"]["attributes"].get("metadata", {}).get("log_errors", False)
                )
            time.sleep(1)
        return None

    @contextmanager
    def report_step(
        self, step_id: str, loading_message: Optional[str] = None, required: bool = True
    ) -> Generator[dict, None, None]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.IN_PROGRESS, f"{step_id}: {Status.IN_PROGRESS}")
        step_complete: Optional[threading.Event] = None
        loading_message_thread: Optional[threading.Thread] = None
        try:
            if loading_message:
                step_complete = threading.Event()
                loading_message_thread = threading.Thread(target=loading_spinner, args=(loading_message, step_complete))
                loading_message_thread.daemon = True
                loading_message_thread.start()
            step_metadata = {}
            yield step_metadata
        except Exception as e:
            if step_complete:
                step_complete.set()
            if loading_message_thread:
                loading_message_thread.join()
            if self.EXPIRED_TOKEN_ERROR in repr(e):
                self.report("connection", Status.CANCELLED, f"Azure CLI token expired: {e}")
                raise
            if isinstance(e, UserRetriableError):
                self.report(
                    step_id,
                    Status.WARN,
                    e.user_action_message,
                )
            elif isinstance(e, UserActionRequiredError):
                self.report(
                    step_id,
                    Status.USER_ACTIONABLE_ERROR,
                    e.user_action_message,
                )
            else:
                traceback_message = f"{Status.FAILED}: {traceback.format_exc()}"
                self.report(step_id, Status.FAILING_AWAITING_USER_DECISION, None)
                decision = self._poll_for_user_decision()
                if decision is None:
                    print("Approval wait period expired, no error logs sent to Datadog.")
                elif decision:
                    self.report(step_id, Status.FAILED, traceback_message)
                else:
                    self.report(step_id, Status.FAILED, None)
            if required:
                raise
        else:
            if step_complete:
                step_complete.set()
            if loading_message_thread:
                loading_message_thread.join()
                # leave line blank and cursor at the beginning
                print(f"\r{' ' * 60}", end="")
                print("\r", end="")
            self.report(step_id, Status.FINISHED, f"{step_id}: {Status.FINISHED}", step_metadata or None)


def loading_spinner(message: str, done: threading.Event):
    spinner_chars = ["|", "/", "-", "\\"]
    spinner_char = 0
    while not done.is_set():
        print(f"\r{message}: {spinner_chars[spinner_char]}", end="")
        spinner_char = (spinner_char + 1) % 4
        time.sleep(0.2)
