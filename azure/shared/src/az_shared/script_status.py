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

from az_shared.auth import check_login
from az_shared.errors import (
    AzCliNotAuthenticatedError,
    AzCliNotInstalledError,
    UserActionRequiredError,
    UserRetriableError,
)
from common.requests import Json, dd_request


class Status(Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"
    WARN = "warn"
    USER_ACTIONABLE_ERROR = "USER_ACTIONABLE_ERROR"


@dataclass
class StatusReporter:
    EXPIRED_TOKEN_ERROR = "Lifetime validation failed, the token is expired"

    workflow_type: str
    workflow_id: str

    def report(self, step_id: str, status: Status, message: str, metadata: Optional[Json] = None) -> None:
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
                    f"{Status.WARN}: {traceback.format_exc()}",
                )
            elif isinstance(e, UserActionRequiredError):
                self.report(
                    step_id,
                    Status.USER_ACTIONABLE_ERROR,
                    e.user_action_message,
                )
            else:
                self.report(step_id, Status.FAILED, f"{Status.FAILED}: {traceback.format_exc()}")
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

    def is_valid_workflow_id(self, final_step: str) -> bool:
        """Return True if the workflow ID can be used to start a new workflow.

        A workflow ID is rejected if any non-login step has already failed, or
        if the given ``final_step`` has already been marked finished. Transient
        errors contacting the API are treated as "valid" so the caller can
        proceed; step reporting will surface real connectivity issues.
        """
        try:
            response, http_status = dd_request(
                "GET",
                f"/api/unstable/integration/azure/workflow/{self.workflow_type}/{self.workflow_id}",
            )
        except Exception:
            return True

        if http_status == 404:
            return True

        if http_status != 200:
            return False

        json_response = json.loads(response)
        statuses: list[dict] = (
            json_response.get("data", {}).get("attributes", {}).get("statuses", [])
        )

        if any(
            step.get("status", "") == Status.FAILED.value
            for step in statuses
            if step.get("step", "") != "login"
        ):
            return False

        if any(
            step.get("step", "") == final_step and step.get("status", "") == Status.FINISHED.value
            for step in statuses
        ):
            return False

        return True

    def handle_login_step(self) -> None:
        """Verify Azure CLI auth and report the login step to the workflow API.

        Wraps ``check_login()`` inside ``report_step("login")`` so the step is
        reported as IN_PROGRESS / FINISHED / (WARN|USER_ACTIONABLE_ERROR|FAILED)
        via the standard path. Exits with code 1 on authentication failures
        after reporting so the Datadog UI reflects the terminal state.
        """
        try:
            with self.report_step("login"):
                check_login()
        except AzCliNotInstalledError:
            print(
                "You must install the Azure CLI and log in to run this script.\n"
                "https://learn.microsoft.com/cli/azure/install-azure-cli"
            )
            raise SystemExit(1)
        except AzCliNotAuthenticatedError:
            print("You must be logged in to Azure CLI to run this script.")
            print("Run: az login")
            raise SystemExit(1)
        except Exception:
            print("You must be logged in to Azure CLI to run this script.")
            print("Run: az login")
            raise SystemExit(1)


def loading_spinner(message: str, done: threading.Event):
    spinner_chars = ["|", "/", "-", "\\"]
    spinner_char = 0
    while not done.is_set():
        print(f"\r{message}: {spinner_chars[spinner_char]}", end="")
        spinner_char = (spinner_char + 1) % 4
        time.sleep(0.2)
