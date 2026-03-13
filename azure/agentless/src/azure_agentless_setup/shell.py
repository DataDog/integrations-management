# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shell command utilities."""

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ShellResult:
    """Result of a shell command execution."""

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
    """Run a shell command and return the result."""
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


def az_cli(args: list[str], output_json: bool = True) -> tuple[bool, Any]:
    """Run an Azure CLI command.

    Args:
        args: Arguments to pass to `az` (e.g., ["account", "show"]).
        output_json: Whether to add --output json flag.

    Returns:
        Tuple of (success, parsed_json_or_stderr).
    """
    cmd = ["az"] + args
    if output_json:
        cmd += ["--output", "json"]

    result = run_command(cmd)

    if not result.success:
        return False, result.stderr.strip()

    if output_json and result.stdout.strip():
        try:
            return True, json.loads(result.stdout)
        except json.JSONDecodeError:
            return True, result.stdout.strip()

    return True, result.stdout.strip()


def az_cli_checked(args: list[str], error_message: str, output_json: bool = True) -> Optional[Any]:
    """Run an Azure CLI command and raise on failure.

    Returns:
        Parsed JSON output, or None if no output.

    Raises:
        RuntimeError: If the command fails.
    """
    success, result = az_cli(args, output_json=output_json)
    if not success:
        raise RuntimeError(f"{error_message}: {result}")
    return result
