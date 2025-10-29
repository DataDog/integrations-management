# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import subprocess
from re import search
from time import sleep
from typing import Union

from .errors import AccessError, RateLimitExceededError, RefreshTokenError, ResourceNotFoundError
from .logs import log

AUTH_FAILED_ERROR = "AuthorizationFailed"
AZURE_THROTTLING_ERROR = "TooManyRequests"
REFRESH_TOKEN_EXPIRED_ERROR = "AADSTS700082"
RESOURCE_COLLECTION_THROTTLING_ERROR = "ResourceCollectionRequestsThrottled"
RESOURCE_NOT_FOUND_ERROR = "ResourceNotFound"

INITIAL_RETRY_DELAY = 2  # seconds
RETRY_DELAY_MULTIPLIER = 2
MAX_RETRIES = 7


class AzCmd:
    """Builder for Azure CLI commands."""

    def __init__(self, service: str, action: str):
        """Initialize with service and action (e.g., 'functionapp', 'create')."""
        self.cmd = [service] + action.split()

    def param(self, key: str, value: str) -> "AzCmd":
        """Adds a key-value pair parameter"""
        self.cmd.extend([key, value])
        return self

    def param_list(self, key: str, values: list[str]) -> "AzCmd":
        """Adds a list of parameters with the same key"""
        self.cmd.append(key)
        self.cmd.extend(values)
        return self

    def flag(self, flag: str) -> "AzCmd":
        """Adds a flag to the command"""
        self.cmd.append(flag)
        return self

    def str(self) -> str:
        return "az " + " ".join(self.cmd)


def check_access_error(stderr: str) -> Union[str, None]:
    # Sample:
    # (AuthorizationFailed) The client 'user@example.com' with object id '00000000-0000-0000-0000-000000000000'
    # does not have authorization to perform action 'Microsoft.Storage/storageAccounts/read'
    # over scope '/subscriptions/00000000-0000-0000-0000-000000000000' or the scope is invalid.
    # If access was recently granted, please refresh your credentials.

    client_match = search(r"client '([^']*)'", stderr)
    action_match = search(r"action '([^']*)'", stderr)
    scope_match = search(r"scope '([^']*)'", stderr)

    if not (action_match and scope_match and client_match):
        return

    client = client_match.group(1)
    action = action_match.group(1)
    scope = scope_match.group(1)
    return f"Insufficient permissions for {client} to perform {action} on {scope}"


def set_subscription(sub_id: str):
    """Set the active Azure subscription."""
    log.debug(f"Setting active subscription to {sub_id}")
    execute(AzCmd("account", "set").param("--subscription", sub_id))


def list_users_subscriptions() -> dict[str, str]:
    user_subs = execute(AzCmd("account", "list").param("--output", "json"))
    subs_json = json.loads(user_subs)
    return {sub["id"]: sub["name"] for sub in subs_json}


def execute(az_cmd: AzCmd, can_fail: bool = False) -> str:
    """Run an Azure CLI command and return output or raise error."""

    full_command = az_cmd.str()
    log.debug(f"Running: {full_command}")
    delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(full_command, shell=True, check=True, capture_output=True, text=True)
            if result.returncode != 0 and not can_fail:
                log.error(f"Command failed: {full_command}")
                log.error(result.stderr)
                raise RuntimeError(f"Command failed: {full_command}")
            return result.stdout
        except subprocess.CalledProcessError as e:
            stderr = str(e.stderr)
            if RESOURCE_NOT_FOUND_ERROR in stderr:
                raise ResourceNotFoundError(f"Resource not found when executing '{az_cmd.str()}'") from e
            if AZURE_THROTTLING_ERROR in stderr or RESOURCE_COLLECTION_THROTTLING_ERROR in stderr:
                if attempt < MAX_RETRIES - 1:
                    log.warning(f"Azure throttling ongoing. Retrying in {delay} seconds...")
                    sleep(delay)
                    delay *= RETRY_DELAY_MULTIPLIER
                    continue
                raise RateLimitExceededError("Rate limit exceeded. Please wait a few minutes and try again.") from e
            if REFRESH_TOKEN_EXPIRED_ERROR in stderr:
                raise RefreshTokenError(f"Auth token is expired. Refresh token before running '{az_cmd.str()}'") from e
            if AUTH_FAILED_ERROR in stderr:
                error_message = f"Insufficient permissions to access resource when executing '{az_cmd.str()}'"
                error_details = check_access_error(stderr)
                if error_details:
                    raise AccessError(f"{error_message}: {error_details}") from e
                raise AccessError(error_message) from e
            if can_fail:
                return ""
            log.error(f"Command failed: {full_command}")
            log.error(e.stderr)
            raise RuntimeError(f"Command failed: {full_command}") from e

    raise SystemExit(1)  # unreachable
