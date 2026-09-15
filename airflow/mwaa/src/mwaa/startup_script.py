# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Renders the MWAA startup script content Datadog's onboarding doc asks customers to add.

Source: https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow.md

The real Datadog API key is never known to this tool -- it's selected in the
Datadog UI at apply time, not by this script -- so `<DD_API_KEY>` is a literal
placeholder in the rendered content, matching the UI mockup exactly.
"""

# Airflow versions that need the OpenLineage config-path workaround, per the
# onboarding doc: fixed upstream in apache-airflow-providers-openlineage 1.7,
# but MWAA's default constraints for these two versions pin older than that.
VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND = {"2.7.2", "2.8.1"}

DD_API_KEY_PLACEHOLDER = "<DD_API_KEY>"


def render_startup_script(airflow_version: str, dd_site: str) -> str:
    """Render the startup.sh content for one environment's Airflow version."""
    lines = [
        "#!/bin/sh",
        f"export OPENLINEAGE_URL=https://data-obs-intake.{dd_site}",
        f"export OPENLINEAGE_API_KEY={DD_API_KEY_PLACEHOLDER}",
        "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}",
    ]
    if airflow_version in VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND:
        lines += [
            'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""',
            'export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""',
        ]
    return "\n".join(lines) + "\n"


# Either mechanism routes lineage events somewhere: OPENLINEAGE_URL is what
# Datadog's current onboarding doc recommends (read directly by the
# OpenLineage client); AIRFLOW__OPENLINEAGE__TRANSPORT is an older/alternate
# JSON-config mechanism some existing environments (e.g. do-test-env's) still
# use. Treating only the former as "configured" produced a false positive
# against a real environment using the latter -- proposing to overwrite a
# transport it already had, just via the other mechanism.
_TRANSPORT_MARKERS = ("OPENLINEAGE_URL=", "AIRFLOW__OPENLINEAGE__TRANSPORT=")


def startup_script_looks_configured(startup_script_text: "str | None") -> bool:
    """Heuristic for the UI's "Configured on Data Observability" column.

    True if the startup script already exports a variable that routes
    lineage events to Datadog, via either supported mechanism.
    """
    if startup_script_text is None:
        return False
    return any(marker in startup_script_text for marker in _TRANSPORT_MARKERS)
