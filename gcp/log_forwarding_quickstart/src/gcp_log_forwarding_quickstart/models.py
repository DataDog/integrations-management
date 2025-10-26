# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import dataclass


# https://cloud.google.com/sdk/gcloud/reference/logging/sinks/create#--exclusion
@dataclass
class ExclusionFilter:
    """Log Sink Exclusion Filter

    Attributes:
        filter: An advanced log filter that matches the log entries to be excluded (required)
        name: A name for the exclusion (required)
    """

    filter: str
    name: str
