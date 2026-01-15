# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Secret Manager utilities for storing the Datadog API key."""

from typing import Optional

from gcp_shared.gcloud import GcloudCmd, gcloud, try_gcloud
from .errors import SecretManagerError
from .reporter import Reporter


API_KEY_SECRET_NAME = "datadog-agentless-scanner-api-key"


def get_secret_id(project: str) -> str:
    """Get the full secret ID for a project."""
    return f"projects/{project}/secrets/{API_KEY_SECRET_NAME}"


def is_secret_existing(project: str) -> bool:
    """Check if the API key secret exists in the project."""
    result = try_gcloud(
        GcloudCmd("secrets", "describe")
        .arg(API_KEY_SECRET_NAME)
        .param("--project", project)
    )
    return result.success


def get_secret_value(project: str) -> Optional[str]:
    """Get the latest version of the secret value.

    Returns:
        The secret value, or None if the secret doesn't exist or has no versions.
    """
    result = try_gcloud(
        GcloudCmd("secrets", "versions", "access")
        .arg("latest")
        .param("--secret", API_KEY_SECRET_NAME)
        .param("--project", project)
    )

    if not result.success:
        return None

    # gcloud returns the raw secret data (not JSON for this command)
    if isinstance(result.data, str):
        return result.data.strip()
    return None


def create_secret(project: str, api_key: str) -> None:
    """Create a new secret with the API key.

    Raises:
        SecretManagerError: If secret creation fails.
    """
    result = try_gcloud(
        GcloudCmd("secrets", "create")
        .arg(API_KEY_SECRET_NAME)
        .param("--project", project)
        .flag("--replication-policy=automatic")
    )

    if not result.success:
        raise SecretManagerError(
            f"Failed to create secret: {API_KEY_SECRET_NAME}",
            result.error,
        )

    add_secret_version(project, api_key)


def add_secret_version(project: str, api_key: str) -> None:
    """Add a new version to the secret with the API key value.

    Raises:
        SecretManagerError: If adding the version fails.
    """
    # Use echo to pipe the secret value to gcloud
    # This avoids having the API key in command line arguments
    import subprocess

    cmd = f'echo -n "{api_key}" | gcloud secrets versions add {API_KEY_SECRET_NAME} --project={project} --data-file=-'

    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise SecretManagerError(
            f"Failed to add secret version to: {API_KEY_SECRET_NAME}",
            proc.stderr,
        )


def ensure_api_key_secret(
    reporter: Reporter,
    project: str,
    api_key: str,
) -> str:
    """Create or update the API key secret in Secret Manager.

    If the secret doesn't exist, creates it.
    If the secret exists with a different value, adds a new version.
    If the secret exists with the same value, does nothing.

    Args:
        reporter: Reporter for progress output.
        project: GCP project ID.
        api_key: Datadog API key to store.

    Returns:
        Full secret ID in format: projects/{project}/secrets/{secret_name}

    Raises:
        SecretManagerError: If secret operations fail.
    """
    secret_id = get_secret_id(project)

    if not is_secret_existing(project):
        # Secret doesn't exist - create it
        reporter.info(f"Creating secret in project {project}...")
        create_secret(project, api_key)
        reporter.success(f"API key stored: {secret_id}")
    else:
        # Secret exists - check if value matches
        current_value = get_secret_value(project)

        if current_value == api_key:
            reporter.success(f"API key secret exists (unchanged): {secret_id}")
        else:
            # Value is different - add new version
            reporter.info(f"Updating secret in project {project}...")
            add_secret_version(project, api_key)
            reporter.success(f"API key secret updated: {secret_id}")

    return secret_id

