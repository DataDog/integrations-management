# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Optional

from az_shared.errors import UserActionRequiredError
from azure_integration_quickstart.util import Json, dd_request


class Status(Enum):
    STARTED = "STARTED"
    OK = "OK"
    ERROR = "ERROR"
    USER_ACTIONABLE_ERROR = "USER_ACTIONABLE_ERROR"


@dataclass
class StatusReporter:
    EXPIRED_TOKEN_ERROR = "Lifetime validation failed, the token is expired"

    workflow_id: str

    def report(self, step_id: str, status: Status, message: str, metadata: Optional[Json] = None) -> None:
        """Report the status of a step in a workflow to Datadog."""
        attributes: dict[str, Json] = {"message": message, "status": status.value, "step_id": step_id}
        if metadata:
            attributes["metadata"] = metadata
        dd_request(
            "POST",
            "/api/unstable/integration/azure/setup/status",
            {"data": {"id": self.workflow_id, "type": "add_azure_app_registration", "attributes": attributes}},
        )

    @contextmanager
    def report_step(
        self, step_id: str, loading_message: Optional[str] = None, required: bool = True
    ) -> Generator[dict, None, None]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.STARTED, f"{step_id}: {Status.STARTED}")
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
                self.report("connection", Status.ERROR, f"Azure CLI token expired: {e}")
                raise
            if isinstance(e, UserActionRequiredError):
                self.report(
                    step_id,
                    Status.USER_ACTIONABLE_ERROR,
                    f"{str(e)}",  # pass along only the message which should be user-readable
                )
            else:
                self.report(step_id, Status.ERROR, f"{step_id}: {Status.ERROR}: {traceback.format_exc()}")
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
            self.report(step_id, Status.OK, f"{step_id}: {Status.OK}", step_metadata or None)


def loading_spinner(message: str, done: threading.Event):
    spinner_chars = ["|", "/", "-", "\\"]
    spinner_char = 0
    while not done.is_set():
        print(f"\r{message}: {spinner_chars[spinner_char]}", end="")
        spinner_char = (spinner_char + 1) % 4
        time.sleep(0.2)
