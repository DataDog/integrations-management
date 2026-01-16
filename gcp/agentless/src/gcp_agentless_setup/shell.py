# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shell command utilities for terraform commands."""

import subprocess
from dataclasses import dataclass
from typing import List


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
    cmd: List[str],
    capture_output: bool = True,
) -> ShellResult:
    """Run a shell command and return the result.

    For any shell command (like terraform) where we need raw stdout/stderr.
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

