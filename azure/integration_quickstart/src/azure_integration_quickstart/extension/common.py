# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from az_shared.execute_cmd import execute
from common.shell import Cmd


def set_dynamic_install_without_prompt() -> None:
    """Configure the Azure CLI to install CLI extensions without prompting the user."""
    execute(Cmd(["az", "config", "set"]).arg("extension.use_dynamic_install=yes_without_prompt"))
