# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Plain HTTPS requests that aren't AWS calls: GETs for the public files a plan is
built from (upstream Airflow constraints files on GitHub, Datadog's patched wheels
on docs.datadoghq.com), and check_intake_api_key's one POST to the Datadog intake.

None of it touches `scan`'s read-only promise -- MwaaClient's guard is about the
customer's AWS account. The GETs are unauthenticated and send nothing about it.
"""

import urllib.error
import urllib.request
from typing import Optional


class FetchError(Exception):
    """A public file couldn't be downloaded."""


def fetch_bytes(url: str, timeout: float = 30.0) -> bytes:
    """GET a public file over HTTPS -- anything else is refused, since its content ends up in the customer's environment."""
    if not url.startswith("https://"):
        raise FetchError(f"refusing to download {url}: not an https:// URL")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"could not download {url}: {exc}") from exc


def check_intake_api_key(dd_site: str, api_key: str, timeout: float = 10.0) -> Optional[bool]:
    """Whether Datadog's intake for `dd_site` accepts `api_key`: True on 2xx, False on 401/403, None if it can't tell.

    POSTs an empty `{}` lineage event, the same request a misconfigured
    environment would make. The key is only ever sent in the Authorization
    header, never printed or kept.
    """
    request = urllib.request.Request(
        f"https://data-obs-intake.{dd_site}/api/v1/lineage",
        data=b"{}",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True if 200 <= response.status < 300 else None
    except urllib.error.HTTPError as exc:
        return False if exc.code in (401, 403) else None
    except (urllib.error.URLError, OSError):
        return None
