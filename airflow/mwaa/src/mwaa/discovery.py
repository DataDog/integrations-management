# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Discovers every MWAA environment in one region and fetches each one's config files."""

from airflow_shared.mwaa_client import MwaaClient

from .checks import ProbeContext
from .probe import build_context


def discover_environments(client: MwaaClient) -> list[ProbeContext]:
    """Fetch a ProbeContext (environment + its config files) for every environment in the region.

    One environment failing to read (permissions, an unexpected state, a
    malformed config) shouldn't abort the scan for every other environment in
    the account -- it's skipped, with a warning printed, instead.
    """
    contexts = []
    for name in client.list_environment_names():
        try:
            contexts.append(build_context(client, name))
        except Exception as e:  # noqa: BLE001 - any failure here is a per-environment skip, not a scan failure
            print(f"  ! skipping {name}: {e}")
    return contexts
