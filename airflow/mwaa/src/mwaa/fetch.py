# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Plain HTTPS GETs for the public files a plan is built from: upstream Airflow
constraints files (GitHub) and Datadog's patched wheels (docs.datadoghq.com).

Not an AWS call, so fetching here from `scan` doesn't touch its read-only
promise -- MwaaClient's guard is about the customer's account, and nothing
here is authenticated or sends anything about it.
"""

import urllib.error
import urllib.request


class FetchError(Exception):
    """A public file couldn't be downloaded."""


def fetch_bytes(url: str, timeout: float = 30.0) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"could not download {url}: {exc}") from exc
