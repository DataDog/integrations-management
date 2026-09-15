# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Known-broken-default -> target package versions for flagged Airflow versions.

Source: Datadog's MWAA/OpenLineage upgrade guide
(https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow_mwaa_upgrade.md),
which documents exact before/after package pins for the three Airflow versions
whose MWAA-default constraints pin a known-broken OpenLineage provider release:
2.7.2, 2.8.1, and 2.9.2.

This table is deliberately hardcoded and versioned in this repo rather than
fetched from a Datadog API at runtime -- per the decision to keep plan
computation client-side for now, so iterating on it doesn't require a backend
deploy. When Datadog's upgrade guide changes, this table needs a matching edit.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlaggedVersionEntry:
    """Target package pins for one flagged Airflow version.

    `default_versions` is what Datadog's guide documents as the broken
    MWAA-default pin, kept for the rationale text -- the actual diff always
    compares against the environment's real current pins, not this default,
    since a customer may have already partially customized their setup.
    """

    airflow_version: str
    default_versions: dict[str, str]
    target_versions: dict[str, str]
    # Packages that must be installed from a Datadog-hosted wheel file instead
    # of a plain version pin. Only true for 2.7.2, where the upstream provider
    # isn't compatible with that Airflow version at all.
    wheel_only_packages: tuple[str, ...] = field(default_factory=tuple)


SOURCE_DOC = "https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow_mwaa_upgrade.md"

FLAGGED_VERSION_TABLE: dict[str, FlaggedVersionEntry] = {
    "2.7.2": FlaggedVersionEntry(
        airflow_version="2.7.2",
        default_versions={
            "apache-airflow-providers-openlineage": "1.1.0",
            "apache-airflow-providers-common-sql": "1.7.2",
            "openlineage-integration-common": "1.3.1",
            "openlineage-python": "1.3.1",
            "openlineage-sql": "1.3.1",
        },
        target_versions={
            "apache-airflow-providers-openlineage": "1.14.0",
            "apache-airflow-providers-common-compat": "1.2.2",
            "openlineage-integration-common": "1.24.2",
            "openlineage-python": "1.24.2",
            "openlineage-sql": "1.24.2",
            # apache-airflow-providers-common-sql: no change needed at 1.7.2.
        },
        wheel_only_packages=("apache-airflow-providers-openlineage", "apache-airflow-providers-common-compat"),
    ),
    "2.8.1": FlaggedVersionEntry(
        airflow_version="2.8.1",
        default_versions={
            "apache-airflow-providers-openlineage": "1.4.0",
            "apache-airflow-providers-common-sql": "1.10.0",
            "openlineage-integration-common": "1.7.0",
            "openlineage-python": "1.7.0",
            "openlineage-sql": "1.7.0",
        },
        target_versions={
            "apache-airflow-providers-openlineage": "1.14.0",
            "apache-airflow-providers-common-sql": "1.20.0",
            "apache-airflow-providers-common-compat": "1.2.1",
            "openlineage-integration-common": "1.24.2",
            "openlineage-python": "1.24.2",
            "openlineage-sql": "1.24.2",
        },
    ),
    "2.9.2": FlaggedVersionEntry(
        airflow_version="2.9.2",
        default_versions={
            "apache-airflow-providers-openlineage": "1.8.0",
            "apache-airflow-providers-common-sql": "1.14.0",
            "openlineage-integration-common": "1.16.0",
            "openlineage-python": "1.16.0",
            "openlineage-sql": "1.16.0",
        },
        target_versions={
            "apache-airflow-providers-openlineage": "2.2.0",
            "apache-airflow-providers-common-sql": "1.21.0",
            "apache-airflow-providers-common-compat": "1.4.0",
            "openlineage-integration-common": "1.31.0",
            "openlineage-python": "1.31.0",
            "openlineage-sql": "1.31.0",
        },
    ),
}
