# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntegrationConfiguration:
    """Holds configuration details for the GCP integration with Datadog."""

    metric_namespace_configs: list[dict[str, Any]]
    monitored_resource_configs: list[dict[str, list[str]]]
    account_tags: list[str]
    resource_collection_enabled: bool
    automute: bool

    region_filter_configs: list[str] = field(default_factory=list)
    is_global_location_enabled: bool = True


@dataclass
class ProductRequirements:
    """Holds product requirements for a downstream Datadog product."""

    required_roles: list[str]
    required_apis: list[str]
