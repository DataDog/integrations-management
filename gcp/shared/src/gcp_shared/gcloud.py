# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import sys
import shlex
import subprocess
from typing import Any, Union


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


def is_logged_in() -> bool:
    """Check if the user is logged in to GCloud CLI."""
    try:
        return gcloud("auth print-access-token") is not None
    except Exception as e:
        if "gcloud: command not found" in str(e):
            print(
                "You must install the GCloud CLI and log in to run this script.\n"
                "https://cloud.google.com/sdk/docs/install"
            )
        else:
            print("You must be logged in to GCloud CLI to run this script.")
        sys.exit(1)
    return False


def gcloud(cmd: Union[str, GcloudCmd], *keys: str) -> Any:
    """Run gcloud CLI command and produce its output. Raise an exception if it fails.

    Args:
        cmd: Either a command string or a GcloudCmd object
        *keys: Optional keys to extract from JSON output

    Returns:
        Parsed JSON output or specific keys from the output
    """

    try:
        gcloud_output_format = "json" if len(keys) == 0 else f'"json({",".join(keys)})"'
        proc_result = subprocess.run(
            f"gcloud {cmd} --format={gcloud_output_format}",
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"could not execute gcloud command '{cmd}': {str(e.stderr)}")
    else:
        return json.loads(proc_result.stdout)
