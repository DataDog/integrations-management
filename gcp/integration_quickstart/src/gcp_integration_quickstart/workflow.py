# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import time
from typing import Any

from .gcloud import gcloud
from .requests import dd_request


def ensure_login() -> None:
    """Ensure that the user is logged into the GCloud Shell. If not, raise an exception."""
    if not gcloud("auth print-access-token"):
        raise RuntimeError("not logged in to GCloud Shell")


def receive_user_selections(workflow_id: str) -> dict[str, Any] | None:
    """Receive user selections from the Datadog workflow."""

    while True:
        response, status = dd_request(
            "GET",
            f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{workflow_id}",
        )

        if status == 404 or not response:
            time.sleep(1)
            continue

        json_response = json.loads(response)

        selections: dict[str, Any] = (
            json_response["data"]["attributes"].get("metadata", {}).get("selections")
        )

        if not selections:
            time.sleep(1)
            continue

        return selections


def is_valid_workflow_id(workflow_id: str) -> bool:
    """Check if the workflow ID can be used to start a new workflow."""
    response, status = dd_request(
        "GET",
        f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{workflow_id}",
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
        step.get("step", "") == "create_integration_with_permissions"
        and step.get("status", "") == "finished"
        for step in statuses
    ):
        return False

    return True


def is_scopes_step_already_completed(
    workflow_id: str,
) -> bool:
    """Check if the scopes step has already been completed in the GCP integration workflow."""

    response, status = dd_request(
        "GET",
        f"/api/unstable/integration/gcp/workflow/gcp-integration-setup/{workflow_id}",
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
