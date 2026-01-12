# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, Union


@dataclass
class CommandResult:
    """Result of a gcloud command execution."""

    returncode: int
    data: Any  # Parsed JSON output (or None on error)
    error: str  # Error message from stderr

    @property
    def success(self) -> bool:
        """Returns True if the command succeeded."""
        return self.returncode == 0


class GcloudCmd:
    """Builder for gcloud CLI commands."""

    def __init__(self, service: str, action: str):
        """Initialize with service and action (e.g., 'pubsub topics', 'create')."""
        self.cmd: list[str] = service.split() + action.split()

    def __str__(self) -> str:
        """Overload string representation to return the full command string with proper shell quoting."""
        return " ".join(shlex.quote(part) for part in self.cmd)

    def arg(self, value: str) -> "GcloudCmd":
        """Adds a positional argument."""
        self.cmd.append(value)
        return self

    def param(self, key: str, value: str) -> "GcloudCmd":
        """Adds a key-value pair parameter (e.g., '--project', 'my-project')."""
        self.cmd.extend([key, value])
        return self

    def param_equals(self, key: str, value: str) -> "GcloudCmd":
        """Adds a key=value parameter (e.g., '--filter=name:foo')."""
        self.cmd.append(f"{key}={value}")
        return self

    def flag(self, flag: str) -> "GcloudCmd":
        """Adds a flag to the command (e.g., '--quiet')."""
        self.cmd.append(flag)
        return self


def gcloud(cmd: Union[str, GcloudCmd], *keys: str) -> Any:
    """Run gcloud CLI command and produce its output. Raise an exception if it fails.

    Args:
        cmd: Either a command string or a GcloudCmd object
        *keys: Optional keys to extract from JSON output

    Returns:
        Parsed JSON output or specific keys from the output

    Raises:
        RuntimeError: If command fails.
    """
    result = try_gcloud(cmd, *keys)
    if not result.success:
        raise RuntimeError(f"could not execute gcloud command '{cmd}': {result.error}")
    return result.data


def try_gcloud(cmd: Union[str, GcloudCmd], *keys: str) -> CommandResult:
    """Run gcloud CLI command and return a CommandResult. Never raises exceptions.

    Args:
        cmd: Either a command string or a GcloudCmd object
        *keys: Optional keys to extract from JSON output

    Returns:
        CommandResult with returncode, data (parsed JSON), and error (stderr).
    """
    gcloud_output_format = "json" if len(keys) == 0 else f'"json({",".join(keys)})"'
    proc_result = subprocess.run(
        f"gcloud {cmd} --format={gcloud_output_format}",
        shell=True,
        check=False,
        text=True,
        capture_output=True,
    )

    if proc_result.returncode != 0:
        return CommandResult(
            returncode=proc_result.returncode,
            data=None,
            error=proc_result.stderr,
        )

    try:
        data = json.loads(proc_result.stdout)
    except json.JSONDecodeError:
        data = proc_result.stdout

    return CommandResult(
        returncode=proc_result.returncode,
        data=data,
        error="",
    )


def is_authenticated() -> bool:
    """Check if gcloud is authenticated."""
    result = try_gcloud(GcloudCmd("auth", "list"))
    if not result.success:
        return False
    return any(acc.get("status") == "ACTIVE" for acc in (result.data or []))


def get_current_project() -> Optional[str]:
    """Get the current gcloud project."""
    result = try_gcloud(GcloudCmd("config", "get-value").arg("project"))
    if result.success and result.data and isinstance(result.data, str):
        return result.data.strip() or None
    return None
