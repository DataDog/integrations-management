# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

def format_error_details(message: str) -> str:
    return f"\n\nError Details:\n{message}"

# Errors that prevent the script from completing successfully
class FatalError(Exception):
    """An error that prevents the installation from completing successfully."""


class TimeoutError(FatalError):
    """Timeout occurred when waiting for a resource to be ready."""


class ExistenceCheckError(FatalError):
    """Error occurred while checking if a resource exists."""


class RefreshTokenError(FatalError):
    """Auth token has expired."""


# Expected Errors
class RateLimitExceededError(Exception):
    """We have exceeded the rate limit for the Azure API. Script will retry until MAX_RETRIES are reached."""


class ResourceNotFoundError(Exception):
    """Azure resource was not found. This gets thrown during some resource existence checks."""


# Errors users can resolve through manual action
class UserActionRequiredError(Exception):
    """An error that requires user action to resolve."""

    def __init__(self, message: str, user_action_message: str | None = None):
        super().__init__(message)
        self.user_action_message = user_action_message or message


class AzCliNotAuthenticatedError(UserActionRequiredError):
    """Azure CLI is not authenticated. User needs to run 'az login'."""

    def __init__(self, message: str = "Azure CLI is not authenticated"):
        super().__init__(
            message,
            user_action_message="Azure CLI is not authenticated. Please run 'az login' first and retry"
        )


class AccessError(UserActionRequiredError):
    """Not authorized to access the resource."""

    def __init__(self, message: str):
        user_action_message = "You don't have the necessary Azure permissions to access, create, or perform an action on a required resource."
        user_action_message += "\nPlease review the Datadog documentation (https://docs.datadoghq.com/getting_started/integrations/azure/) and contact your Azure administrator if necessary."
        user_action_message += format_error_details(message)
        super().__init__(message, user_action_message)


class InputParamValidationError(UserActionRequiredError):
    """Validation error in user input parameters."""

    def __init__(self, message: str):
        user_action_message = "Invalid input parameter. Please check your input(s) and try again."
        user_action_message += format_error_details(message)
        super().__init__(message, user_action_message)


class ResourceProviderRegistrationValidationError(UserActionRequiredError):
    """Resource provider is not registered."""

    def __init__(self, message: str):
        user_action_message = "Log Forwarding requires all monitored subscriptions to register all of the following Azure resource providers: Microsoft.CloudShell, Microsoft.Web, Microsoft.App, Microsoft.Storage, and Microsoft.Authorization."
        user_action_message += "\nOne of your Azure subscriptions does not have all of the required registrations."
        user_action_message += "\nPlease register the missing resource providers in the Azure Portal or contact your Azure administrator."
        user_action_message += format_error_details(message)
        super().__init__(message, user_action_message)


class DatadogAccessValidationError(UserActionRequiredError):
    """Not authorized to access Datadog - API key and site need to be configured correctly."""

    def __init__(self, message: str):
        user_action_message = "Unable to authenticate with Datadog. Please verify the Datadog API key and Datadog site are configured correctly."
        user_action_message += format_error_details(message)
        super().__init__(message, user_action_message)



