# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from re import search

from az_shared.util import get_az_and_python_version


# Errors that prevent script from completing successfully
class AzIntegrationError(Exception):
    """Base exception that appends python and az version details to the error message."""

    def __init__(self, error_message: str):
        super().__init__(f"{error_message}{get_az_and_python_version()}")


class FatalError(AzIntegrationError):
    """An error that prevents the installation from completing successfully."""


class TimeoutError(FatalError):
    """Timeout occurred when waiting for a resource to be ready."""


class ExistenceCheckError(FatalError):
    """Error occurred when checking if a resource exists."""


def format_error_details(error_message: str) -> str:
    return f"\n\nError Details:\n{error_message}"


# Errors users can resolve through manual action
class UserActionRequiredError(AzIntegrationError):
    """An error that requires user action to resolve."""

    def __init__(self, error_message: str, user_action_message: str):
        self.user_action_message = user_action_message
        super().__init__(error_message)


class AppRegistrationCreationPermissionsError(UserActionRequiredError):
    """Not authorized to create an app registration."""

    def __init__(self, error_message: str):
        user_action_message = "Please ensure that you have the permissions necessary to create an App Registration, as described here: https://docs.datadoghq.com/getting_started/integrations/azure/?tab=createanappregistration#permission-to-create-an-app-registration. If you have recently been granted these permissions, please allow up to an hour for them to propagate."
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class AccessError(UserActionRequiredError):
    """Not authorized to access an Azure resource."""

    def __init__(self, error_message: str):
        user_action_message = "You don't have the necessary Azure permissions to access, create, or perform an action on a required resource."
        user_action_message += "\nPlease review the Datadog documentation at https://docs.datadoghq.com/getting_started/integrations/azure/ and contact your Azure administrator if necessary."
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class InputParamValidationError(UserActionRequiredError):
    """Validation error in user input parameters."""

    def __init__(self, error_message: str):
        user_action_message = "Invalid input parameter. Please check your input(s) and try again."
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class ResourceProviderRegistrationValidationError(UserActionRequiredError):
    """Resource provider is not registered."""

    def __init__(self, error_message: str):
        user_action_message = "Log Forwarding requires all monitored subscriptions to register all of the following Azure resource providers: Microsoft.CloudShell, Microsoft.Web, Microsoft.App, Microsoft.Storage, and Microsoft.Authorization."
        user_action_message += "\nOne of your Azure subscriptions does not have all of the required registrations."
        user_action_message += (
            "\nPlease register the missing resource providers in the Azure Portal or contact your Azure administrator."
        )
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class DatadogAccessValidationError(UserActionRequiredError):
    """Not authorized to access Datadog - API key and site need to be configured correctly."""

    def __init__(self, error_message: str):
        user_action_message = "Unable to authenticate with Datadog. Please verify the Datadog API key and Datadog site are configured correctly."
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class InteractiveAuthenticationRequiredError(UserActionRequiredError):
    """Must authenticate interactively to request additional scopes."""

    def __init__(self, commands: list[str], error_message: str) -> None:
        self.commands = commands
        user_action_message = '{}. Run the following Azure CLI commands and then try again: "{}"'.format(
            error_message, " && ".join(commands)
        )
        super().__init__(error_message, user_action_message)


class RefreshTokenError(UserActionRequiredError):
    """Auth token has expired."""

    def __init__(self, error_message: str):
        user_action_message = (
            "Azure auth token is expired. Reauthenticate with `az login` or restart your cloud shell and try again."
        )
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class PolicyError(UserActionRequiredError):
    """User has set a policy incompatible with some piece of the Datadog integration."""

    def __init__(self, error_message: str):
        policy_name_match = search(r'"policyDefinition":{"name":"([^"]*)"', error_message)
        policy_name = policy_name_match.group(1) if policy_name_match else ""
        user_action_message = f"Unable to create Datadog integration due to your policy {policy_name}. In order to install the Datadog integration you will have to modify this policy or select scopes where it does not apply."
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class DisabledSubscriptionError(UserActionRequiredError):
    """The current Azure subscription is disabled."""

    def __init__(self, error_message: str):
        super().__init__(
            error_message,
            'The Azure subscription you are currently logged into is disabled. Select a different subscription with "az account set --subscription <subscription_id>" before trying again.',
        )


class UserRetriableError(UserActionRequiredError):
    """An error that requires user action to resolve, after which the user can simply retry the script rather than reloading the page."""


class AzCliNotInstalledError(UserRetriableError):
    """Azure CLI is not installed. User needs to install az cli."""

    def __init__(self, error_message: str):
        user_action_message = "You must install and log in to Azure CLI to run this script"
        user_action_message += format_error_details(error_message)
        super().__init__(error_message, user_action_message)


class AzCliNotAuthenticatedError(UserRetriableError):
    """Azure CLI is not authenticated. User needs to run 'az login'."""

    def __init__(self, error_message: str):
        super().__init__(error_message, error_message)


# Expected Errors
class RateLimitExceededError(AzIntegrationError):
    """We have exceeded the rate limit for the Azure API. Script will retry until MAX_RETRIES are reached."""


class ResourceNotFoundError(AzIntegrationError):
    """Azure resource was not found. This gets thrown during some resource existence checks."""
