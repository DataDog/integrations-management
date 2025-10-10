# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import subprocess
from typing import Any


def gcloud(cmd: str, *keys: str) -> Any:
    """Run gcloud CLI command and produce its output. Raise an exception if it fails."""
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
