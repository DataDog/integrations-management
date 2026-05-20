# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Exception classes for the Azure agentless scanner setup.

Extends the shared az_shared.errors hierarchy so that all agentless errors
are also AzIntegrationError instances (includes az/python version in str()).
"""

import functools
import inspect
from typing import Callable, Optional, TypeVar

from az_shared.errors import FatalError

F = TypeVar("F", bound=Callable[..., object])


class SetupError(FatalError):
    """Base exception for agentless setup errors.

    Extends shared FatalError so errors include az/python version info.
    Adds a `detail` attribute for structured error reporting.
    """

    def __init__(self, message: str, detail: Optional[str] = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class ConfigurationError(SetupError):
    """Error in configuration/environment variables."""


class DatadogCredentialsError(SetupError):
    """Invalid Datadog credentials."""

    pass


class DatadogAPIKeyError(DatadogCredentialsError):
    """Invalid Datadog API key or site."""

    def __init__(self, site: str):
        super().__init__(
            "Invalid Datadog API key or site",
            f"Please verify your DD_API_KEY and DD_SITE ({site}) are correct.",
        )


class DatadogAPIKeyMissingRCError(DatadogCredentialsError):
    """API key missing Remote Configuration scope."""

    def __init__(self):
        super().__init__(
            "API key missing Remote Configuration scope",
            "Please ensure your DD_API_KEY has Remote Configuration enabled.\n"
            "You can enable it in Datadog under Organization Settings > API Keys.",
        )


class DatadogAppKeyError(DatadogCredentialsError):
    """Invalid Datadog Application key."""

    def __init__(self):
        super().__init__(
            "Invalid Datadog Application key",
            "Please verify your DD_APP_KEY is correct and belongs to the same organization.",
        )


class AzureAccessError(SetupError):
    """Cannot access an Azure resource or insufficient permissions."""


class ResourceProviderError(SetupError):
    """Failed to register a required Azure resource provider."""


class StorageAccountError(SetupError):
    """Failed to create or access an Azure Storage Account."""


class KeyVaultError(SetupError):
    """Error during Key Vault operations."""


class MetadataError(SetupError):
    """Error reading/writing deployment metadata."""


class TerraformError(SetupError):
    """Terraform operation failed."""


def wrap_az_errors(
    error_cls: type[SetupError],
    message_template: str,
) -> Callable[[F], F]:
    """Wrap unexpected exceptions raised by ``func`` as ``error_cls``.

    Replaces the recurring ``try / except Exception as e: raise
    <DomainError>(f"Failed to ...", str(e)) from e`` boilerplate around
    ``az`` CLI helpers in :mod:`state_storage` and :mod:`secrets`.
    Already-typed instances of ``error_cls`` propagate untouched so a
    caller raising a more specific message via its own ``raise`` is not
    re-wrapped.

    The decorated function's bound arguments are exposed to
    ``message_template`` via ``str.format``, so e.g.::

        @wrap_az_errors(StorageAccountError,
                        "Failed to create storage account: {account_name}")
        def create_storage_account(account_name: str, ...): ...

    pulls ``account_name`` directly from the call. Defaults are filled
    in via :meth:`inspect.BoundArguments.apply_defaults` before the
    template is rendered.
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_cls:
                raise
            except Exception as e:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                raise error_cls(
                    message_template.format(**bound.arguments),
                    str(e),
                ) from e

        return wrapper  # type: ignore[return-value]

    return decorator
