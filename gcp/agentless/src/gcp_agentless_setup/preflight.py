# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Preflight checks before running Terraform."""

import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import json

from .config import Config
from .errors import (
    APIEnablementError,
    DatadogAPIKeyError,
    DatadogAPIKeyMissingRCError,
    DatadogAppKeyError,
    GCPAccessError,
    GCPAuthenticationError,
)
from gcp_shared.gcloud import GcloudCmd, gcloud, is_authenticated
from .reporter import Reporter, AgentlessStep


# Maximum number of parallel workers for API/project operations
MAX_PARALLEL_WORKERS = 10

# APIs that must be enabled in the scanner project
SCANNER_PROJECT_APIS = [
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",  # For Terraform state bucket
]

# APIs that must be enabled in scanned projects
SCANNED_PROJECT_APIS = [
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
]


def validate_datadog_api_key(reporter: Reporter, api_key: str, site: str) -> None:
    """Validate Datadog API key and check for Remote Configuration scope.

    Raises:
        DatadogAPIKeyError: If the API key or site is invalid.
        DatadogAPIKeyMissingRCError: If the API key doesn't have Remote Configuration scope.
    """
    url = f"https://api.{site}/api/v2/validate"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "DD-API-KEY": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                scopes = data.get("data", {}).get("attributes", {}).get("api_key_scopes", [])
                if "remote_config_read" not in scopes:
                    raise DatadogAPIKeyMissingRCError()
                reporter.success("Datadog API key validated (Remote Configuration enabled)")
            else:
                raise DatadogAPIKeyError(site)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise DatadogAPIKeyError(site)
        raise DatadogAPIKeyError(site)
    except urllib.error.URLError:
        raise DatadogAPIKeyError(site)


def validate_datadog_app_key(reporter: Reporter, api_key: str, app_key: str, site: str) -> None:
    """Validate Datadog Application key.

    Raises:
        DatadogAppKeyError: If the Application key is invalid.
    """
    url = f"https://api.{site}/api/v2/validate_keys"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                reporter.success("Datadog Application key validated")
                return
            else:
                raise DatadogAppKeyError()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise DatadogAppKeyError()
        raise DatadogAppKeyError()
    except urllib.error.URLError:
        raise DatadogAppKeyError()


def check_gcp_authentication(reporter: Reporter) -> None:
    """Verify GCP authentication.

    Raises:
        GCPAuthenticationError: If not authenticated with GCP.
    """
    if not is_authenticated():
        raise GCPAuthenticationError()
    reporter.success("GCP authentication verified")


def check_project_access(project: str) -> tuple[str, bool, Optional[str]]:
    """Check if we have access to a project.

    Returns:
        Tuple of (project, success, error_message)
    """
    try:
        gcloud(GcloudCmd("projects", "describe").arg(project))
        return project, True, None
    except RuntimeError as e:
        return project, False, str(e)


def check_projects_access_parallel(reporter: Reporter, projects: list[str]) -> list[str]:
    """Check access to multiple projects in parallel.

    Returns:
        List of projects that failed access check.
    """
    failed_projects = []

    with ThreadPoolExecutor(max_workers=min(len(projects), MAX_PARALLEL_WORKERS)) as executor:
        futures = {executor.submit(check_project_access, p): p for p in projects}

        for future in as_completed(futures):
            project, success, error = future.result()
            if not success:
                reporter.error(f"Cannot access project: {project}", error)
                failed_projects.append(project)

    return failed_projects


def enable_apis_batch(project: str, apis: list[str]) -> tuple[bool, Optional[str]]:
    """Enable multiple APIs in a single gcloud command.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Build command with all APIs as arguments
        cmd = GcloudCmd("services", "enable")
        for api in apis:
            cmd.arg(api)
        cmd.param("--project", project)

        gcloud(cmd)
        return True, None
    except RuntimeError as e:
        return False, str(e)


def check_and_enable_apis(
    reporter: Reporter,
    project: str,
    required_apis: list[str],
) -> None:
    """Check and enable required APIs in a project.

    Uses batch enablement for efficiency.

    Raises:
        GCPAccessError: If APIs cannot be listed.
        APIEnablementError: If APIs cannot be enabled.
    """
    # Get currently enabled APIs
    try:
        services = gcloud(
            GcloudCmd("services", "list")
            .flag("--enabled")
            .param("--project", project)
        )
    except RuntimeError as e:
        raise GCPAccessError(
            f"Cannot list APIs for project: {project}",
            str(e),
        )

    enabled_apis = set()
    for service in (services or []):
        # API names in list are like "compute.googleapis.com"
        name = service.get("config", {}).get("name", "")
        if name:
            enabled_apis.add(name)

    # Find missing APIs
    missing_apis = [api for api in required_apis if api not in enabled_apis]

    if not missing_apis:
        return

    # Enable all missing APIs in a single batch command
    reporter.info(f"Enabling {len(missing_apis)} API(s) in {project}...")
    success, error = enable_apis_batch(project, missing_apis)

    if not success:
        raise APIEnablementError(
            f"Failed to enable APIs in {project}",
            error,
        )


def enable_apis_for_projects_parallel(
    reporter: Reporter,
    projects: list[str],
    required_apis: list[str],
) -> None:
    """Enable APIs for multiple projects in parallel.

    Raises:
        APIEnablementError: If APIs cannot be enabled for any project.
    """
    errors = []

    def enable_for_project(project: str) -> tuple[str, Optional[str]]:
        try:
            check_and_enable_apis(reporter, project, required_apis)
            return project, None
        except (GCPAccessError, APIEnablementError) as e:
            return project, str(e)

    with ThreadPoolExecutor(max_workers=min(len(projects), MAX_PARALLEL_WORKERS)) as executor:
        futures = {executor.submit(enable_for_project, p): p for p in projects}

        for future in as_completed(futures):
            project, error = future.result()
            if error:
                errors.append((project, error))

    if errors:
        error_details = "\n".join(f"  - {p}: {e}" for p, e in errors)
        raise APIEnablementError(
            f"Failed to enable APIs in {len(errors)} project(s)",
            error_details,
        )


def run_preflight_checks(config: Config, reporter: Reporter) -> None:
    """Run all preflight checks.

    Uses parallel execution for faster completion.

    Raises:
        GCPAuthenticationError: If not authenticated with GCP.
        GCPAccessError: If projects cannot be accessed.
        APIEnablementError: If APIs cannot be enabled.
    """
    reporter.start_step("Validating prerequisites", AgentlessStep.PREFLIGHT_CHECKS)

    # Check GCP authentication
    check_gcp_authentication(reporter)

    # Check access to all projects in parallel
    reporter.info(f"Checking access to {len(config.all_projects)} project(s)...")
    failed_projects = check_projects_access_parallel(reporter, config.all_projects)

    if failed_projects:
        raise GCPAccessError(
            f"Cannot access {len(failed_projects)} project(s)",
            "Ensure you have 'resourcemanager.projects.get' permission on:\n"
            + "\n".join(f"  - {p}" for p in failed_projects),
        )

    reporter.success(f"Access verified for {len(config.all_projects)} project(s)")

    # Enable APIs in scanner project (has more APIs, do separately)
    reporter.info(f"Checking APIs in scanner project ({config.scanner_project})...")
    check_and_enable_apis(reporter, config.scanner_project, SCANNER_PROJECT_APIS)
    reporter.success("Scanner project APIs ready")

    # Enable APIs in other scanned projects in parallel
    if config.other_projects:
        reporter.info(f"Checking APIs in {len(config.other_projects)} scanned project(s)...")
        enable_apis_for_projects_parallel(reporter, config.other_projects, SCANNED_PROJECT_APIS)
        reporter.success("Scanned project APIs ready")
