# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import os
import ssl
import time
import urllib.request
from typing import Any, Tuple
from urllib.error import HTTPError, URLError


def request(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] = {},
    max_retries: int = 3,
    base_delay: float = 1.0,
    retry_status_codes: set[int] = {500, 502, 503, 504},
) -> Tuple[str, int]:
    """Submit a request to the given URL with the specified method and body with retry logic."""

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            method=method,
            headers=headers,
            data=json.dumps(body).encode("utf-8") if body else None,
        )

        try:
            with urllib.request.urlopen(
                req, context=ssl.create_default_context()
            ) as response:
                data, status = response.read().decode("utf-8"), response.status
                return data, status
        except HTTPError as e:
            data, status = e.read().decode("utf-8"), e.code
            if status in retry_status_codes:
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2**attempt))
                    continue

                raise RuntimeError(f"HTTP error {status}: {data}")

            return data, status
        except URLError as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2**attempt))
                continue

            raise RuntimeError(
                f"Network error after {max_retries} attempts: {e.reason}"
            ) from e


def dd_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> Tuple[str, int]:
    """Submit a request to Datadog."""
    return request(
        method,
        f"https://api.{os.environ['DD_SITE']}{path}",
        body,
        {
            "Content-Type": "application/json",
            "DD-API-KEY": os.environ["DD_API_KEY"],
            "DD-APPLICATION-KEY": os.environ["DD_APP_KEY"],
        },
    )

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generator



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
