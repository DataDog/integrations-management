# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Preflight checks before running Terraform."""

from .config import Config
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
    """Verify GCP authentication."""
    if not check_gcloud_auth():
        reporter.fatal(
            "Not authenticated with GCP",
            "Run: gcloud auth login",
        )
    reporter.success("GCP authentication verified")


def check_project_access(reporter: Reporter, project: str) -> bool:
    """Check if we have access to a project."""
    result = gcloud(
        GcloudCmd("projects", "describe")
        .arg(project)
    )

    if not result.success:
        reporter.error(
            f"Cannot access project: {project}",
            result.stderr,
        )
        return False

    return True


def enable_api(reporter: Reporter, project: str, api: str) -> bool:
    """Enable an API in a project."""
    result = gcloud(
        GcloudCmd("services", "enable")
        .arg(api)
        .with_project(project)
    )

    if not result.success:
        reporter.error(
            f"Failed to enable {api} in {project}",
            result.stderr,
        )
        return False

    return True


def check_and_enable_apis(
    reporter: Reporter,
    project: str,
    required_apis: list[str],
) -> bool:
    """Check and enable required APIs in a project."""
    # Get currently enabled APIs
    result = gcloud(
        GcloudCmd("services", "list")
        .flag("--enabled")
        .with_project(project)
    )

    if not result.success:
        reporter.error(
            f"Cannot list APIs for project: {project}",
            result.stderr,
        )
        return False

    enabled_apis = set()
    for service in (result.json() or []):
        # API names in list are like "compute.googleapis.com"
        name = service.get("config", {}).get("name", "")
        if name:
            enabled_apis.add(name)

    # Enable missing APIs
    missing_apis = [api for api in required_apis if api not in enabled_apis]

    for api in missing_apis:
        reporter.info(f"Enabling {api} in {project}...")
        if not enable_api(reporter, project, api):
            return False

    return True


def run_preflight_checks(config: Config, reporter: Reporter) -> None:
    """Run all preflight checks."""
    step = reporter.start_step("Validating prerequisites")

    # Check GCP authentication
    check_gcp_authentication(reporter)

    # Check access to all projects
    reporter.info("Checking project access...")
    failed_projects = []
    for project in config.all_projects:
        if not check_project_access(reporter, project):
            failed_projects.append(project)

    if failed_projects:
        reporter.fatal(
            f"Cannot access {len(failed_projects)} project(s)",
            "Ensure you have 'resourcemanager.projects.get' permission on:\n"
            + "\n".join(f"  - {p}" for p in failed_projects),
        )

    reporter.success(f"Access verified for {len(config.all_projects)} project(s)")

    # Enable APIs in scanner project
    reporter.info(f"Checking APIs in scanner project ({config.scanner_project})...")
    if not check_and_enable_apis(reporter, config.scanner_project, SCANNER_PROJECT_APIS):
        reporter.fatal("Failed to enable required APIs in scanner project")
    reporter.success("Scanner project APIs ready")

    # Enable APIs in other scanned projects
    if config.other_projects:
        reporter.info(f"Checking APIs in {len(config.other_projects)} scanned project(s)...")
        for project in config.other_projects:
            if not check_and_enable_apis(reporter, project, SCANNED_PROJECT_APIS):
                reporter.fatal(f"Failed to enable required APIs in {project}")
        reporter.success("Scanned project APIs ready")

