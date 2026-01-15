# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Exception classes for the agentless scanner setup."""

from typing import Optional


class SetupError(Exception):
    """Base exception for setup errors."""

    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigurationError(SetupError):
    """Error in configuration/environment variables."""


class GCPAuthenticationError(SetupError):
    """Not authenticated with GCP."""

    def __init__(self, message: str = "Not authenticated with GCP"):
        super().__init__(
            message,
            "Run: gcloud auth login",
        )


class GCPAccessError(SetupError):
    """Cannot access a GCP resource."""


class APIEnablementError(SetupError):
    """Failed to enable a required GCP API."""


class BucketCreationError(SetupError):
    """Failed to create a GCS bucket."""


class SecretManagerError(SetupError):
    """Error during Secret Manager operations."""


class TerraformError(SetupError):
    """Terraform operation failed."""


class UserInterruptError(SetupError):
    """User interrupted the script (Ctrl+C)."""

    def __init__(self):
        super().__init__("Setup interrupted by user")

