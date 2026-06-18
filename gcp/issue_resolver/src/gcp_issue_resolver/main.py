# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import logging
import os
import sys
from typing import Any, Optional

from gcp_shared.ensure_permissions import ensure_service_account_permissions, is_valid_service_account_email
from gcp_shared.gcloud import GcloudCmd, gcloud
from gcp_shared.requests import dd_request

log = logging.getLogger(__name__)

# Canonical source: gcp/integration_quickstart/src/gcp_integration_quickstart/integration_configuration.py
REQUIRED_ROLES: list[str] = [
    "roles/cloudasset.viewer",
    "roles/browser",
    "roles/compute.viewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
]

REQUIRED_ENV_VARS: set[str] = {"DD_API_KEY", "DD_APP_KEY", "DD_SITE"}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _check_env_vars()
    email, project_ids = _parse_args(sys.argv)
    if not is_valid_service_account_email(email):
        raise ValueError(f"Invalid service account email: '{email}'")
    reporter = LoggingStepReporter()
    fix_permissions(reporter, email, project_ids)
    log.info("Done. All permissions applied successfully.")


def fix_permissions(reporter: "LoggingStepReporter", email: str, project_ids: list[str]) -> None:
    for project_id in project_ids:
        log.info(f"Fixing permissions for project '{project_id}'...")
        ensure_service_account_permissions(reporter, project_id, email, REQUIRED_ROLES)
    _apply_delegate_permissions(reporter, email, _project_from_email(email))


def _apply_delegate_permissions(reporter: "LoggingStepReporter", email: str, project_id: str) -> None:
    reporter.report(message=f"Fetching Datadog STS delegate for service account '{email}'...")
    response, status = dd_request("GET", "/api/v2/integration/gcp/sts_delegate")
    if status != 200 or not response:
        raise RuntimeError("Failed to get STS delegate from Datadog API")
    datadog_principal = json.loads(response)["data"]["id"]
    reporter.report(message=f"Assigning [roles/iam.serviceAccountTokenCreator] to '{datadog_principal}' on '{email}'")
    gcloud(
        GcloudCmd("iam service-accounts", "add-iam-policy-binding")
        .arg(email)
        .param("--member", f"serviceAccount:{datadog_principal}")
        .param("--role", "roles/iam.serviceAccountTokenCreator")
        .param("--condition", "None")
        .param("--project", project_id)
        .flag("--quiet")
    )


def _check_env_vars() -> None:
    missing = REQUIRED_ENV_VARS - os.environ.keys()
    if missing:
        log.error(f"Missing required environment variables: {', '.join(sorted(missing))}")
        sys.exit(1)


def _parse_args(argv: list[str]) -> tuple[str, list[str]]:
    if len(argv) < 3:
        log.error("Usage: python -m gcp_issue_resolver.main <email> <project_id> [<project_id> ...]")
        sys.exit(1)
    return argv[1], argv[2:]


def _project_from_email(email: str) -> str:
    return email.split("@")[1].split(".")[0]


class LoggingStepReporter:
    def report(self, message: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> None:
        if message:
            log.info(message)


if __name__ == "__main__":
    main()
