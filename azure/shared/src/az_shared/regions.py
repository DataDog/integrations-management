# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure region discovery utilities."""

from az_shared.execute_cmd import execute_json
from common.shell import Cmd


def get_available_regions() -> list[str]:
    """Return the Azure region names available to the current tenant.

    Calls ``az account list-locations`` once and returns the list of names
    (e.g. ``["eastus", "westeurope", …]``).
    """
    return execute_json(
        Cmd(["az", "account", "list-locations"])
        .param("--query", "[].name")
        .param("-o", "json")
    )
