# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

# Errors that prevent script from completing successfully
class FatalError(Exception):
    """An error that prevents the installation from completing successfully."""


class TimeoutError(FatalError):
    """Timeout occurred when waiting for a resource to be ready."""


class ExistenceCheckError(FatalError):
    """Error occurred when checking if a resource exists."""


# Errors users can resolve through manual action
class UserActionRequiredError(Exception):
    """An error that requires user action to resolve."""


class AccessError(UserActionRequiredError):
    """Not authorized to access the resource."""


class InputParamValidationError(UserActionRequiredError):
    """Validation error in user input parameters."""


class ResourceProviderRegistrationValidationError(UserActionRequiredError):
    """Resource provider is not registered."""


class ResourceNameAvailabilityError(UserActionRequiredError):
    """Resource name is not available."""


class DatadogAccessValidationError(UserActionRequiredError):
    """Not authorized to access Datadog - API key and site need to be configured correctly."""


class UserRetriableError(UserActionRequiredError):
    """An error that requires user action to resolve, after which the user can simply retry the script rather than reloading the page."""


class AzCliNotInstalledError(UserRetriableError):
    """Azure CLI is not installed. User needs to install az cli."""


class AzCliNotAuthenticatedError(UserRetriableError):
    """Azure CLI is not authenticated. User needs to run 'az login'."""


class InteractiveAuthenticationRequiredError(UserRetriableError):
    """Must authenticate interactively to request additional scopes."""

    def __init__(self, commands: list[str], *args: object) -> None:
        self.commands = commands
        super().__init__(*args)


class RefreshTokenError(UserActionRequiredError):
    """Auth token has expired."""


# Expected Errors
class RateLimitExceededError(Exception):
    """We have exceeded the rate limit for the Azure API. Script will retry until MAX_RETRIES are reached."""


class ResourceNotFoundError(Exception):
    """Azure resource was not found. This gets thrown during some resource existence checks."""
