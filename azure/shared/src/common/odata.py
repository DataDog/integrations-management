# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from typing import Any
from urllib.parse import urlencode


def odata_query(**kwargs: Any) -> str:
    return urlencode({f"${k}": v for k, v in kwargs.items()})
