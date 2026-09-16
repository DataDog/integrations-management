# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared configuration-parsing error for scan_config.py and apply_config.py."""


class ConfigError(Exception):
    """Missing or invalid configuration."""
