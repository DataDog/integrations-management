# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from logging import getLogger

log = getLogger("logging_installer")


def log_header(message: str):
    """Log a formatted header message."""
    separator = "=" * 70
    header = "\n".join(["", separator, message, separator, ""])
    log.info(header)
