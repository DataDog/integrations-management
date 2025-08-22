#!/usr/bin/env python3

# Errors that prevent script from completing successfully
class FatalError(Exception):
    """An error that prevents the installation from completing successfully."""

    pass


class TimeoutError(FatalError):
    """An error that indicates a timeout occurred when waiting for a resource to be ready."""

    pass


class ExistenceCheckError(FatalError):
    """An error that occurs when checking if a resource exists."""

    pass


class RefreshTokenError(FatalError):
    """An error that indicates our auth token has expired."""

    pass


# Errors users can resolve through manual action
class UserActionRequiredError(Exception):
    """An error that requires user action to resolve."""

    pass


class AccessError(UserActionRequiredError):
    """An error that indicates we are not authorized to access the resource."""

    pass


class InputParamValidationError(UserActionRequiredError):
    """An error that indicates a validation error in user input parameters."""

    pass


class ResourceProviderRegistrationValidationError(UserActionRequiredError):
    """An error that indicates a resource provider is not registered."""

    pass


class ResourceNameAvailabilityError(UserActionRequiredError):
    """An error that indicates a resource name is not available."""

    pass


class DatadogAccessValidationError(UserActionRequiredError):
    """An error that indicates we are not authorized to access Datadog."""

    pass


# Expected Errors
class RateLimitExceededError(Exception):
    """An error that indicates we have exceeded the rate limit for the Azure API. Script will retry until MAX_RETRIES are reached."""

    pass


class ResourceNotFoundError(Exception):
    """An error that indicates a resource was not found. This gets thrown during some resource existence checks."""

    pass
