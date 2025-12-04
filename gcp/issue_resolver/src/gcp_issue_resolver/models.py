# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass
from typing import Any


@dataclass
class IssueResolverConfiguration:
    """Holds configuration details for the GCP issue resolver."""

    issue_types: list[str]
    auto_fix_enabled: bool
    dry_run: bool
    notification_preferences: dict[str, Any]


