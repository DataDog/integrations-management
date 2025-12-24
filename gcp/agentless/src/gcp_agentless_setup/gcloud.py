# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""GCloud CLI wrapper utilities."""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional


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
        if not self.stdout.strip():
            return None
        return json.loads(self.stdout)


def run_command(
    cmd: list[str],
    capture_output: bool = True,
    check: bool = False,
) -> CommandResult:
    """Run a shell command and return the result."""
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
    )

    cmd_result = CommandResult(
        returncode=result.returncode,
        stdout=result.stdout if capture_output else "",
        stderr=result.stderr if capture_output else "",
    )

    if check and not cmd_result.success:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{cmd_result.stderr}")

    return cmd_result


@dataclass
class GcloudCmd:
    """Fluent builder for gcloud commands."""

    service: str
    action: str
    args: list[str] = field(default_factory=list)
    params: list[tuple[str, str]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    project: Optional[str] = None

    def arg(self, value: str) -> "GcloudCmd":
        """Add a positional argument."""
        self.args.append(value)
        return self

    def param(self, key: str, value: str) -> "GcloudCmd":
        """Add a --key value parameter."""
        self.params.append((key, value))
        return self

    def flag(self, flag: str) -> "GcloudCmd":
        """Add a boolean flag."""
        self.flags.append(flag)
        return self

    def with_project(self, project: str) -> "GcloudCmd":
        """Set the project for this command."""
        self.project = project
        return self

    def build(self) -> list[str]:
        """Build the command as a list of strings."""
        cmd = ["gcloud"] + self.service.split() + [self.action]
        cmd.extend(self.args)

        for key, value in self.params:
            cmd.extend([key, value])

        cmd.extend(self.flags)

        if self.project:
            cmd.extend(["--project", self.project])

        # Always use JSON format for parsing
        cmd.extend(["--format", "json"])

        return cmd


def gcloud(cmd: GcloudCmd) -> CommandResult:
    """Execute a gcloud command."""
    return run_command(cmd.build())


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    result = run_command(["gcloud", "auth", "list", "--format", "json"])
    if not result.success:
        return False

    accounts = result.json()
    return any(acc.get("status") == "ACTIVE" for acc in (accounts or []))


def get_current_project() -> Optional[str]:
    """Get the current gcloud project."""
    result = run_command(["gcloud", "config", "get-value", "project"])
    if result.success and result.stdout.strip():
        return result.stdout.strip()
    return None

