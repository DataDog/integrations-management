# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Renders the MWAA startup script content Datadog's onboarding doc asks customers to add.

Source: https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow.md

The rendered content NEVER carries the real Datadog API key -- only
DD_API_KEY_PLACEHOLDER. A Plan (and by extension a persisted Session) is meant
to be safe to ship to a backend and store; baking the real key into that would
mean every place a Session gets persisted, logged, or displayed becomes a place
a customer's real API key could leak. The real value is substituted in by
interpolate_api_key, called by apply.py right before a file actually gets
written to S3 (or previewed at the terminal) -- the only two places the real
key is used, and neither of those persists anything.

The doc's own snippet uses `AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}`
as if AIRFLOW_ENV_NAME is already set, but it isn't one of MWAA's reserved or
commonly-set variables (see AWS's own startup-script docs) -- nothing defines
it, so that line would silently resolve to an empty namespace. Since a real
MWAA deployment is typically one of several (dev/staging/prod are usually
separate environments, not one Airflow instance switching contexts), and each
environment's own Name is already the natural, unique way to tell them apart,
this substitutes the real environment name directly into the namespace line
instead -- no intermediate variable, no indirection.
"""

# Airflow versions that need the OpenLineage config-path workaround, per the
# onboarding doc: fixed upstream in apache-airflow-providers-openlineage 1.7,
# but MWAA's default constraints for these two versions pin older than that.
VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND = {"2.7.2", "2.8.1"}

#: Stands in for the real API key in any rendered/persisted startup.sh content.
#: See the module docstring for why the real value never appears there.
DD_API_KEY_PLACEHOLDER = "<DD_API_KEY>"


def render_startup_script(airflow_version: str, dd_site: str, environment_name: str) -> str:
    """Render the startup.sh content for one environment's Airflow version.

    Carries DD_API_KEY_PLACEHOLDER, never a real key -- see interpolate_api_key.
    """
    lines = [
        "#!/bin/sh",
        f"export OPENLINEAGE_URL=https://data-obs-intake.{dd_site}",
        f"export OPENLINEAGE_API_KEY={DD_API_KEY_PLACEHOLDER}",
        f'export AIRFLOW__OPENLINEAGE__NAMESPACE="{environment_name}"',
    ]
    if airflow_version in VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND:
        lines += [
            'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""',
            'export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""',
        ]
    return "\n".join(lines) + "\n"


def interpolate_api_key(content: str, dd_api_key: str) -> str:
    """Substitute the real Datadog API key into rendered startup.sh content.

    Called by apply.py right before a file is written or previewed -- the only
    two places the real key is ever used. Everything upstream of that (Plan,
    Session, any persisted/logged/displayed form of either) only ever carries
    DD_API_KEY_PLACEHOLDER.
    """
    return content.replace(DD_API_KEY_PLACEHOLDER, dd_api_key)


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
