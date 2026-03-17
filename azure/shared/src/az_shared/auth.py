# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Azure CLI authentication and subscription helpers."""

from az_shared.errors import AzCliNotAuthenticatedError, AzCliNotInstalledError
from az_shared.execute_cmd import execute
from common.shell import Cmd


def check_login() -> str:
    """Verify Azure CLI is installed and the current user is authenticated.

    Returns:
        The JSON output from ``az account show``.

    Raises:
        AzCliNotInstalledError: If Azure CLI is not installed.
        AzCliNotAuthenticatedError: If the user is not logged in.
    """
    try:
        return execute(Cmd(["az", "account", "show", "--output", "json"]))
    except AzCliNotInstalledError:
        raise
    except AzCliNotAuthenticatedError:
        raise
    except Exception as e:
        msg = str(e)
        if "az: command not found" in msg or "az: not found" in msg:
            raise AzCliNotInstalledError(msg) from e
        raise AzCliNotAuthenticatedError(msg) from e


def set_subscription(subscription_id: str) -> None:
    """Set the active Azure subscription.

    Args:
        subscription_id: The Azure subscription ID to activate.

    Raises:
        Inherits from ``execute``: ``AccessError``, ``RuntimeError``, etc.
    """
    execute(Cmd(["az", "account", "set", "--subscription", subscription_id]))
