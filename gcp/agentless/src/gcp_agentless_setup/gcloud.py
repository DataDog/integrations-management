# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""GCloud CLI wrapper utilities.

This module re-exports from gcp_shared for consistency with other GCP modules,
and provides additional helper functions specific to agentless setup.
"""

import subprocess
from dataclasses import dataclass

# Re-export from gcp_shared for consistency
from gcp_shared.gcloud import CommandResult, GcloudCmd, gcloud, try_gcloud


@dataclass
class ShellResult:
    """Result of a shell command execution (for non-gcloud commands like terraform)."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_command(
    cmd: list[str],
    capture_output: bool = True,
) -> ShellResult:
    """Run a shell command and return the result.

    For non-gcloud commands (like terraform) where we need raw stdout/stderr.
    """
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
    )

    return ShellResult(
        returncode=result.returncode,
        stdout=result.stdout if capture_output else "",
        stderr=result.stderr if capture_output else "",
    )


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    result = try_gcloud(GcloudCmd("auth", "list"))
    if not result.success:
        return False
    return any(acc.get("status") == "ACTIVE" for acc in (result.data or []))


def get_current_project() -> str | None:
    """Get the current gcloud project."""
    result = try_gcloud(GcloudCmd("config", "get-value").arg("project"))
    if result.success and result.data and isinstance(result.data, str):
        return result.data.strip() or None
    return None


# Re-export for backward compatibility
__all__ = [
    "CommandResult",
    "GcloudCmd",
    "ShellResult",
    "check_gcloud_auth",
    "gcloud",
    "get_current_project",
    "run_command",
    "try_gcloud",
]
