# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Is OpenLineage effectively configured? Judged statically from requirements.txt, startup.sh and
AirflowConfigurationOptions, following the provider's and openlineage-python's own precedence."""

import pytest

from airflow_shared.reporter import FindingStatus
from mwaa.checks import ProbeContext
from mwaa.plan import EnvVarChange
from mwaa.session import build_session

SITE = "datad0g.com"
INTAKE = "https://data-obs-intake.datad0g.com"
PROVIDER = "apache-airflow-providers-openlineage\n"

DOCS_RECIPE = (
    "#!/bin/sh\n"
    f"export OPENLINEAGE_URL={INTAKE}\n"
    "export OPENLINEAGE_API_KEY=0123456789abcdef\n"
    "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}\n"
)
WORKAROUND = 'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""\nexport AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""\n'
NAMESPACE = "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}\n"


def entry_for(startup: "str | None", *, airflow_version: str = "2.10.3", requirements: str = PROVIDER, config_options: "dict | None" = None):
    ctx = ProbeContext(
        environment={
            "Name": "my-env",
            "AirflowVersion": airflow_version,
            "SourceBucketArn": "arn:aws:s3:::example-bucket",
            "DagS3Path": "dags",
            "AirflowConfigurationOptions": config_options or {},
        },
        requirements_text=requirements,
        constraints_text=None,
        startup_script_text=startup,
        client=None,
    )
    return build_session("s", "us-east-1", SITE, [ctx]).environments[0]


def check(entry, check_id: str) -> "tuple[FindingStatus, str] | None":
    return next(((i.status, i.message) for i in entry.issues if i.check_id == check_id), None)


def env_var_names(entry) -> set[str]:
    return {fc.name for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)}


# --- the docs recipe ----------------------------------------------------------------


def test_the_docs_recipe_is_configured():
    entry = entry_for(DOCS_RECIPE)

    assert entry.already_configured is True
    assert entry.plan.file_changes == []
    assert check(entry, "openlineage_transport") is None


def test_the_docs_recipe_for_2_8_1_with_its_workaround_variables_is_configured():
    entry = entry_for(DOCS_RECIPE + WORKAROUND, airflow_version="2.8.1")

    assert entry.already_configured is True
    assert env_var_names(entry) == set()


@pytest.mark.parametrize(
    "missing",
    ["OPENLINEAGE_URL", "OPENLINEAGE_API_KEY", "AIRFLOW__OPENLINEAGE__NAMESPACE"],
)
def test_the_docs_recipe_missing_any_one_variable_is_not_configured(missing):
    startup = "".join(line + "\n" for line in DOCS_RECIPE.splitlines() if missing not in line)

    entry = entry_for(startup)

    assert entry.already_configured is False
    assert missing in env_var_names(entry)


@pytest.mark.parametrize("missing", ["AIRFLOW__OPENLINEAGE__CONFIG_PATH", "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS"])
def test_2_8_1_missing_either_workaround_variable_is_not_configured(missing):
    startup = DOCS_RECIPE + "".join(line + "\n" for line in WORKAROUND.splitlines() if missing not in line)

    entry = entry_for(startup, airflow_version="2.8.1")

    assert entry.already_configured is False
    assert missing in env_var_names(entry)


def test_the_docs_recipe_without_the_provider_in_requirements_is_not_configured():
    entry = entry_for(DOCS_RECIPE, requirements="pandas==2.1.4\n")

    assert entry.already_configured is False
    assert check(entry, "openlineage_provider") is None  # nothing suggests it's installed some other way


def test_a_provider_only_installed_by_the_startup_script_is_a_warning():
    startup = DOCS_RECIPE + "pip install apache-airflow-providers-openlineage==2.14.0 --no-deps || true\n"

    entry = entry_for(startup, requirements="pandas==2.1.4\n")

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_provider")
    assert status == FindingStatus.WARN
    assert "startup script" in message


def test_an_intake_url_with_a_path_is_configured():
    assert entry_for(DOCS_RECIPE.replace(INTAKE, f"{INTAKE}/api/v1/lineage")).already_configured is True


def test_openlineage_url_pointing_at_another_site_is_corrected_without_a_failure():
    entry = entry_for(DOCS_RECIPE.replace(INTAKE, "https://data-obs-intake.datadoghq.com"))

    assert entry.already_configured is False
    assert "OPENLINEAGE_URL" in env_var_names(entry)
    assert check(entry, "openlineage_transport") is None  # the plan fixes it, so nothing blocks apply


# --- shell resolution ------------------------------------------------------------


@pytest.mark.parametrize(
    "url_lines",
    [
        f'export OPENLINEAGE_URL="${{OPENLINEAGE_URL:-{INTAKE}}}"\n',
        f'export OPENLINEAGE_URL="${{OPENLINEAGE_URL-{INTAKE}}}"\n',
        f'BASE={INTAKE}\nexport OPENLINEAGE_URL="$BASE"\n',
        f"BASE={INTAKE}\nexport OPENLINEAGE_URL=${{BASE}}/api/v1/lineage\n",
        f"OPENLINEAGE_URL='{INTAKE}'\nexport OPENLINEAGE_URL\n",
    ],
    ids=["colon-dash-default", "dash-default", "dollar-reference", "braced-reference-with-path", "assigned-then-exported"],
)
def test_shell_expansions_of_the_url_are_resolved(url_lines):
    startup = url_lines + "export OPENLINEAGE_API_KEY=0123456789abcdef\n" + NAMESPACE

    assert entry_for(startup).already_configured is True


@pytest.mark.parametrize(
    "key_lines",
    [
        'export OPENLINEAGE_API_KEY=$(get_secret "example/api-key")\n',
        'DD_API_KEY=$(get_secret "example/dd")\nexport OPENLINEAGE_API_KEY="${OPENLINEAGE_API_KEY:-$DD_API_KEY}"\n',
    ],
    ids=["command-substitution", "default-to-another-variable"],
)
def test_any_non_empty_api_key_expression_counts_as_set(key_lines):
    startup = f"export OPENLINEAGE_URL={INTAKE}\n" + key_lines + NAMESPACE

    entry = entry_for(startup)

    assert entry.already_configured is True
    assert "OPENLINEAGE_API_KEY" not in env_var_names(entry)


def test_an_unset_variable_without_a_default_does_not_count_as_a_url():
    startup = 'export OPENLINEAGE_URL="${SOME_UNSET_URL}"\nexport OPENLINEAGE_API_KEY=0123456789abcdef\n' + NAMESPACE

    entry = entry_for(startup)

    assert entry.already_configured is False
    assert check(entry, "openlineage_transport")[0] == FindingStatus.WARN


def test_a_url_from_command_substitution_cant_be_verified_and_isnt_overwritten():
    startup = "export OPENLINEAGE_URL=$(get_url)\nexport OPENLINEAGE_API_KEY=0123456789abcdef\n" + NAMESPACE

    entry = entry_for(startup)

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert "OPENLINEAGE_URL" in message
    assert "OPENLINEAGE_URL" not in env_var_names(entry)


def test_an_empty_namespace_is_not_set():
    entry = entry_for(DOCS_RECIPE.replace("${AIRFLOW_ENV_NAME}", '""'))

    assert entry.already_configured is False
    assert "AIRFLOW__OPENLINEAGE__NAMESPACE" in env_var_names(entry)


def test_assignments_inside_functions_and_heredocs_are_ignored():
    startup = (
        "configure() {\n"
        "    export OPENLINEAGE_URL=https://inside-a-function.invalid\n"
        "}\n"
        "cat <<EOF > /tmp/x\n"
        "export OPENLINEAGE_URL=https://inside-a-heredoc.invalid\n"
        "EOF\n"
    ) + DOCS_RECIPE

    assert entry_for(startup).already_configured is True


# --- precedence --------------------------------------------------------------------


def test_airflow_transport_to_the_intake_is_configured_without_openlineage_url():
    startup = (
        f"""export AIRFLOW__OPENLINEAGE__TRANSPORT='{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "k"}}}}'\n"""
        + NAMESPACE
    )

    entry = entry_for(startup)

    assert entry.already_configured is True
    assert env_var_names(entry) == set()


@pytest.mark.parametrize("where", ["startup", "config_options"])
def test_airflow_transport_elsewhere_overrides_openlineage_url_and_fails(where):
    transport = '{"type": "http", "url": "https://elsewhere.invalid"}'
    startup = DOCS_RECIPE + (f"export AIRFLOW__OPENLINEAGE__TRANSPORT='{transport}'\n" if where == "startup" else "")
    config_options = {"openlineage.transport": transport} if where == "config_options" else None

    entry = entry_for(startup, config_options=config_options)

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in message
    assert "https://elsewhere.invalid" in message
    assert not env_var_names(entry) & {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"}


def test_a_config_path_wins_over_the_airflow_transport_and_cant_be_verified():
    startup = (
        "export AIRFLOW__OPENLINEAGE__CONFIG_PATH=/usr/local/airflow/dags/openlineage.yml\n"
        f"""export AIRFLOW__OPENLINEAGE__TRANSPORT='{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "k"}}}}'\n"""
        + NAMESPACE
    )

    entry = entry_for(startup)

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert "AIRFLOW__OPENLINEAGE__CONFIG_PATH" in message
    assert not env_var_names(entry) & {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY", "AIRFLOW__OPENLINEAGE__CONFIG_PATH"}


ENV_STYLE_HTTP = (
    "export OPENLINEAGE__TRANSPORT__TYPE=http\n"
    f"export OPENLINEAGE__TRANSPORT__URL={INTAKE}\n"
    "export OPENLINEAGE__TRANSPORT__AUTH__TYPE=api_key\n"
    "export OPENLINEAGE__TRANSPORT__AUTH__API_KEY=k\n" + NAMESPACE
)


def test_an_env_style_http_transport_to_the_intake_is_configured_on_provider_2_6_or_later():
    assert entry_for(ENV_STYLE_HTTP, requirements="apache-airflow-providers-openlineage==2.18.0\n").already_configured is True


def test_an_env_style_only_transport_on_an_unknown_provider_version_cant_be_verified():
    """conf.is_disabled only started counting OPENLINEAGE__TRANSPORT__* env vars in provider 2.6.0."""
    entry = entry_for(ENV_STYLE_HTTP)

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert "2.6.0" in message


def test_an_env_style_only_transport_on_a_provider_before_2_6_is_re_enabled_by_openlineage_url():
    """Before 2.6.0 the provider disables itself here; OPENLINEAGE_URL re-enables it, and the env-style
    transport -- which still wins over OPENLINEAGE_URL -- then sends to the intake."""
    entry = entry_for(ENV_STYLE_HTTP, requirements="apache-airflow-providers-openlineage==1.14.0\n")

    assert entry.already_configured is False
    assert check(entry, "openlineage_transport") is None
    assert "OPENLINEAGE_URL" in env_var_names(entry)


def test_a_composite_picks_up_openlineage_url_through_its_default_http_alias():
    startup = (
        "export OPENLINEAGE__TRANSPORT__TYPE=composite\n"
        "export OPENLINEAGE__TRANSPORT__TRANSPORTS__CONSOLE__TYPE=console\n"
        f"export OPENLINEAGE_URL={INTAKE}\n"
        "export OPENLINEAGE_API_KEY=k\n" + NAMESPACE
    )

    assert entry_for(startup).already_configured is True


def test_a_composite_without_the_intake_is_fixed_through_the_openlineage_url_alias():
    """openlineage-python aliases OPENLINEAGE_URL into the composite as default_http, so setting it takes effect."""
    startup = (
        "export OPENLINEAGE__TRANSPORT__TYPE=composite\n"
        "export OPENLINEAGE__TRANSPORT__TRANSPORTS__CONSOLE__TYPE=console\n" + NAMESPACE
    )

    entry = entry_for(startup, requirements="apache-airflow-providers-openlineage==2.18.0\n")

    assert entry.already_configured is False
    assert check(entry, "openlineage_transport") is None
    assert {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"} <= env_var_names(entry)


def test_a_composite_whose_explicit_default_http_goes_elsewhere_fails():
    startup = (
        "export OPENLINEAGE__TRANSPORT__TYPE=composite\n"
        "export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__TYPE=http\n"
        "export OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__URL=https://elsewhere.invalid\n" + NAMESPACE
    )

    entry = entry_for(startup, requirements="apache-airflow-providers-openlineage==2.18.0\n")

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert "OPENLINEAGE__TRANSPORT__TYPE" in message
    assert "https://elsewhere.invalid" in message
    assert not env_var_names(entry) & {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"}


@pytest.mark.parametrize("variable", ["OPENLINEAGE_DISABLED", "AIRFLOW__OPENLINEAGE__DISABLED"])
def test_disabling_openlineage_fails(variable):
    entry = entry_for(DOCS_RECIPE + f"export {variable}=true\n")

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert variable in message
