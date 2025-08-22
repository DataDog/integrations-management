#!/usr/bin/env python3

# Errors that prevent script from completing successfully
class FatalError(Exception):
    """An error that prevents the installation from completing successfully."""


class TimeoutError(FatalError):
    """An error that indicates a timeout occurred when waiting for a resource to be ready."""


class ExistenceCheckError(FatalError):
    """An error that occurs when checking if a resource exists."""


class RefreshTokenError(FatalError):
    """An error that indicates our auth token has expired."""


# Errors users can resolve through manual action
class UserActionRequiredError(Exception):
    """An error that requires user action to resolve."""


class AccessError(UserActionRequiredError):
    """An error that indicates we are not authorized to access the resource."""


class InputParamValidationError(UserActionRequiredError):
    """An error that indicates a validation error in user input parameters."""


class ResourceProviderRegistrationValidationError(UserActionRequiredError):
    """An error that indicates a resource provider is not registered."""


class ResourceNameAvailabilityError(UserActionRequiredError):
    """An error that indicates a resource name is not available."""


class DatadogAccessValidationError(UserActionRequiredError):
    """An error that indicates we are not authorized to access Datadog."""


# Expected Errors
class RateLimitExceededError(Exception):
    """An error that indicates we have exceeded the rate limit for the Azure API. Script will retry until MAX_RETRIES are reached."""


class ResourceNotFoundError(Exception):
    """An error that indicates a resource was not found. This gets thrown during some resource existence checks."""
