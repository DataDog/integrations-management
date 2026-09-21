# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""What startup.sh needs to export, and reading what it already has.

Source: https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow.md

target_values() is the list of (name, value) pairs Datadog's onboarding doc
asks customers to export. parse_exports() reads the same shape back out of a
real startup script, so plan.py can diff "what's there" against "what's
needed" per variable -- rather than treating the whole file as one opaque
blob to overwrite, which is what this tool used to do and is exactly the bug
that motivated this module's current shape: a customer's unrelated existing
startup.sh content deserves to survive an apply.

OPENLINEAGE_API_KEY's value is never a real key here -- see
DD_API_KEY_PLACEHOLDER. A Plan (and by extension a persisted Session) is
meant to be safe to ship to a backend and store; baking the real key into
that would mean every place a Session gets persisted, logged, or displayed
becomes a place a customer's real API key could leak. The real value is
substituted in by interpolate_api_key, called by apply.py right before a
file actually gets written to S3 (or previewed at the terminal) -- the only
two places the real key is used, and neither of those persists anything.

The doc's own snippet uses `AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}`
as if AIRFLOW_ENV_NAME is already set, but it isn't one of MWAA's reserved or
commonly-set variables (see AWS's own startup-script docs) -- nothing defines
it, so that line would silently resolve to an empty namespace. Since a real
MWAA deployment is typically one of several (dev/staging/prod are usually
separate environments, not one Airflow instance switching contexts), and each
environment's own Name is already the natural, unique way to tell them apart,
this substitutes the real environment name directly into the namespace value
instead -- no intermediate variable, no indirection.
"""

import re

# Airflow versions that need the OpenLineage config-path workaround, per the
# onboarding doc: fixed upstream in apache-airflow-providers-openlineage 1.7,
# but MWAA's default constraints for these two versions pin older than that.
VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND = {"2.7.2", "2.8.1"}

#: Stands in for the real API key in any rendered/persisted content.
#: See the module docstring for why the real value never appears there.
DD_API_KEY_PLACEHOLDER = "<DD_API_KEY>"

#: Variables whose value is never safe to read back and display -- see
#: plan.py's _plan_env_var_changes for why that means we never propose
#: *correcting* one of these (we have no real value to compare against),
#: only adding it when it's missing entirely.
SECRET_VAR_NAMES = frozenset({"OPENLINEAGE_API_KEY"})

_EXPORT_LINE = re.compile(r"^\s*export\s+(AIRFLOW__OPENLINEAGE__\w+|OPENLINEAGE_\w+)=(.*)$", re.MULTILINE)


def _strip_matching_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_exports(text: str) -> dict[str, str]:
    """Read back every OPENLINEAGE_*/AIRFLOW__OPENLINEAGE__* export already in a startup script."""
    return {name: _strip_matching_quotes(value) for name, value in _EXPORT_LINE.findall(text)}


def target_values(airflow_version: str, dd_site: str, environment_name: str) -> list[tuple[str, str]]:
    """The (name, value) pairs startup.sh needs for this environment, in the order they should appear."""
    values = [
        ("OPENLINEAGE_URL", f"https://data-obs-intake.{dd_site}"),
        ("OPENLINEAGE_API_KEY", DD_API_KEY_PLACEHOLDER),
        ("AIRFLOW__OPENLINEAGE__NAMESPACE", environment_name),
    ]
    if airflow_version in VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND:
        values += [
            ("AIRFLOW__OPENLINEAGE__CONFIG_PATH", ""),
            ("AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS", ""),
        ]
    return values


def render_export_line(name: str, value: str) -> str:
    """One `export NAME=value` line, quoted the way this variable needs to be.

    Only NAMESPACE and the (always-empty) workaround variables need quotes;
    URL/API_KEY values never contain characters that do.
    """
    if name == "AIRFLOW__OPENLINEAGE__NAMESPACE" or value == "":
        return f'export {name}="{value}"'
    return f"export {name}={value}"


def interpolate_api_key(content: str, dd_api_key: str) -> str:
    """Substitute the real Datadog API key into rendered startup.sh content.

    Called by apply.py right before a file is written or previewed -- the only
    two places the real key is ever used. Everything upstream of that (Plan,
    Session, any persisted/logged/displayed form of either) only ever carries
    DD_API_KEY_PLACEHOLDER.
    """
    return content.replace(DD_API_KEY_PLACEHOLDER, dd_api_key)
