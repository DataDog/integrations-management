# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""GCloud CLI wrapper utilities.

This module re-exports from gcp_shared for consistency with other GCP modules,
and provides additional helper functions specific to agentless setup.
"""

import subprocess
from dataclasses import dataclass
from typing import Any

# Re-export from gcp_shared for consistency
from gcp_shared.gcloud import GcloudCmd, gcloud


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        """Parse stdout as JSON."""
        import json

        if not self.stdout.strip():
            return None
        return json.loads(self.stdout)


def run_command(
    cmd: list[str],
    capture_output: bool = True,
) -> CommandResult:
    """Run a shell command and return the result.

    Unlike gcloud() which raises on error, this returns a CommandResult
    for cases where we want to handle failures gracefully.
    """
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
    )

    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout if capture_output else "",
        stderr=result.stderr if capture_output else "",
    )


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    try:
        accounts = gcloud(GcloudCmd("auth", "list"))
        return any(acc.get("status") == "ACTIVE" for acc in (accounts or []))
    except RuntimeError:
        return False


def get_current_project() -> str | None:
    """Get the current gcloud project."""
    result = run_command(["gcloud", "config", "get-value", "project"])
    if result.success and result.stdout.strip():
        return result.stdout.strip()
    return None


# Re-export for backward compatibility
__all__ = [
    "GcloudCmd",
    "gcloud",
    "CommandResult",
    "run_command",
    "check_gcloud_auth",
    "get_current_project",
]
