# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Preflight checks before running Terraform."""

from .config import Config
from .errors import APIEnablementError, GCPAccessError, GCPAuthenticationError
from .gcloud import GcloudCmd, gcloud, check_gcloud_auth
from .reporter import Reporter


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


def check_gcp_authentication(reporter: Reporter) -> None:
    """Verify GCP authentication.

    Raises:
        GCPAuthenticationError: If not authenticated with GCP.
    """
    if not check_gcloud_auth():
        raise GCPAuthenticationError()
    reporter.success("GCP authentication verified")


def check_project_access(reporter: Reporter, project: str) -> bool:
    """Check if we have access to a project."""
    try:
        gcloud(GcloudCmd("projects", "describe").arg(project))
        return True
    except RuntimeError as e:
        reporter.error(f"Cannot access project: {project}", str(e))
        return False


def enable_api(reporter: Reporter, project: str, api: str) -> None:
    """Enable an API in a project.

    Raises:
        APIEnablementError: If the API cannot be enabled.
    """
    try:
        gcloud(
            GcloudCmd("services", "enable")
            .arg(api)
            .param("--project", project)
        )
    except RuntimeError as e:
        raise APIEnablementError(
            f"Failed to enable {api} in {project}",
            str(e),
        )


def check_and_enable_apis(
    reporter: Reporter,
    project: str,
    required_apis: list[str],
) -> None:
    """Check and enable required APIs in a project.

    Raises:
        GCPAccessError: If APIs cannot be listed.
        APIEnablementError: If an API cannot be enabled.
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

    # Enable missing APIs
    missing_apis = [api for api in required_apis if api not in enabled_apis]

    for api in missing_apis:
        reporter.info(f"Enabling {api} in {project}...")
        enable_api(reporter, project, api)


def run_preflight_checks(config: Config, reporter: Reporter) -> None:
    """Run all preflight checks.

    Raises:
        GCPAuthenticationError: If not authenticated with GCP.
        GCPAccessError: If projects cannot be accessed.
        APIEnablementError: If APIs cannot be enabled.
    """
    reporter.start_step("Validating prerequisites")

    # Check GCP authentication
    check_gcp_authentication(reporter)

    # Check access to all projects
    reporter.info("Checking project access...")
    failed_projects = []
    for project in config.all_projects:
        if not check_project_access(reporter, project):
            failed_projects.append(project)

    if failed_projects:
        raise GCPAccessError(
            f"Cannot access {len(failed_projects)} project(s)",
            "Ensure you have 'resourcemanager.projects.get' permission on:\n"
            + "\n".join(f"  - {p}" for p in failed_projects),
        )

    reporter.success(f"Access verified for {len(config.all_projects)} project(s)")

    # Enable APIs in scanner project
    reporter.info(f"Checking APIs in scanner project ({config.scanner_project})...")
    check_and_enable_apis(reporter, config.scanner_project, SCANNER_PROJECT_APIS)
    reporter.success("Scanner project APIs ready")

    # Enable APIs in other scanned projects
    if config.other_projects:
        reporter.info(f"Checking APIs in {len(config.other_projects)} scanned project(s)...")
        for project in config.other_projects:
            check_and_enable_apis(reporter, project, SCANNED_PROJECT_APIS)
        reporter.success("Scanned project APIs ready")
