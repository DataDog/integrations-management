# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Is OpenLineage effectively configured? Judged statically from requirements.txt, startup.sh and
AirflowConfigurationOptions, following the provider's and openlineage-python's own precedence."""

import json
from dataclasses import asdict, replace

import pytest

from airflow_shared.reporter import FindingStatus
from mwaa.base_constraints import BaseConstraints
from mwaa.checks import ProbeContext
from mwaa.openlineage_config import analyze, is_any_datadog_intake_url, merge_transport_fields
from mwaa.patch import patch_env_vars
from mwaa.plan import EnvVarChange
from mwaa.session import _env_tag, build_session
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER, interpolate_api_key

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


def entry_for(
    startup: "str | None",
    *,
    airflow_version: str = "2.10.3",
    requirements: str = PROVIDER,
    config_options: "dict | None" = None,
    constraints: "str | None" = None,
    validate_api_key=None,
):
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
        base_constraints=BaseConstraints(source="s3://example-bucket/dags/constraints.txt", text=constraints) if constraints else None,
    )
    return build_session("s", "us-east-1", SITE, [ctx], validate_api_key).environments[0]


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


def test_the_docs_recipe_for_2_8_1_with_only_a_bare_provider_is_not_configured():
    """2.8.1 has to follow the upgrade guide too: target pins under a local, full constraints file."""
    entry = entry_for(DOCS_RECIPE + WORKAROUND, airflow_version="2.8.1")

    assert entry.already_configured is False
    assert env_var_names(entry) == set()  # the transport side is fine; it's the packages


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


COMPLETE_AIRFLOW_TRANSPORT = f"""export AIRFLOW__OPENLINEAGE__TRANSPORT='{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "k"}}}}'\n"""
LEGACY_CONFIG_FILE = "export OPENLINEAGE_CONFIG=/usr/local/airflow/dags/openlineage.yml\n"


def test_a_complete_airflow_transport_still_decides_with_a_legacy_config_file_set():
    """openlineage-python merges the OPENLINEAGE_CONFIG file *below* the config the provider passes in."""
    assert entry_for(COMPLETE_AIRFLOW_TRANSPORT + LEGACY_CONFIG_FILE + NAMESPACE).already_configured is True


def test_an_airflow_transport_elsewhere_still_fails_with_a_legacy_config_file_set():
    startup = """export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://elsewhere.invalid"}'\n""" + LEGACY_CONFIG_FILE + NAMESPACE

    assert check(entry_for(startup), "openlineage_transport")[0] == FindingStatus.FAIL


def test_a_legacy_config_file_that_could_supply_a_missing_api_key_cant_be_verified():
    startup = f"""export AIRFLOW__OPENLINEAGE__TRANSPORT='{{"type": "http", "url": "{INTAKE}"}}'\n""" + LEGACY_CONFIG_FILE + NAMESPACE

    entry = entry_for(startup)

    assert entry.already_configured is False
    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert "OPENLINEAGE_CONFIG" in message


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


# --- version-specific capabilities ---------------------------------------------------


def airflow_transport(transport: str) -> str:
    return f"export AIRFLOW__OPENLINEAGE__TRANSPORT='{transport}'\n" + NAMESPACE


ASYNC_HTTP = airflow_transport(f'{{"type": "async_http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "k"}}}}')
LOWERCASE_APIKEY = airflow_transport(f'{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apikey": "k"}}}}')


@pytest.mark.parametrize(
    "startup, boundary",
    [(ASYNC_HTTP, "1.35.0"), (LOWERCASE_APIKEY, "1.38.0")],
    ids=["async_http", "apikey-spelling"],
)
def test_openlineage_python_capabilities_count_only_from_the_version_that_has_them(startup, boundary):
    at_boundary = entry_for(startup, requirements=PROVIDER + f"openlineage-python=={boundary}\n")
    before = entry_for(startup, requirements=PROVIDER + "openlineage-python==1.24.2\n")
    unknown = entry_for(startup)

    assert at_boundary.already_configured is True
    assert before.already_configured is False
    if boundary == "1.35.0":
        assert check(before, "openlineage_transport")[0] == FindingStatus.FAIL  # async_http can't be fixed by a url or key
    else:
        # the key the pinned client can't see is corrected in place instead
        assert check(before, "openlineage_transport") is None
        assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in env_var_names(before)
    assert unknown.already_configured is False
    status, message = check(unknown, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert boundary in message


def test_the_openlineage_python_version_can_come_from_the_constraints_file():
    entry = entry_for(ASYNC_HTTP, constraints="openlineage-python==1.24.2\n")

    assert check(entry, "openlineage_transport")[0] == FindingStatus.FAIL


def test_config_conn_id_only_counts_on_providers_that_read_it():
    startup = DOCS_RECIPE + "export AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID=openlineage_default\n"

    ignored = entry_for(startup, requirements="apache-airflow-providers-openlineage==2.17.0\n")
    read = entry_for(startup, requirements="apache-airflow-providers-openlineage==2.18.0\n")
    unknown = entry_for(startup)

    assert ignored.already_configured is True
    for entry in (read, unknown):
        assert entry.already_configured is False
        status, message = check(entry, "openlineage_transport")
        assert status == FindingStatus.WARN
        assert "AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID" in message
    assert "2.18.0" in check(unknown, "openlineage_transport")[1]


@pytest.mark.parametrize("kind", ["console", "noop", "kafka", "file"])
def test_a_non_http_airflow_transport_still_fails_with_a_legacy_config_file_set(kind):
    """The file merges below the Airflow transport, so it can't replace that transport's type."""
    entry = entry_for(airflow_transport(f'{{"type": "{kind}"}}') + LEGACY_CONFIG_FILE)

    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in message


def test_an_intake_transport_with_a_non_api_key_auth_is_corrected_even_with_a_legacy_config_file_set():
    entry = entry_for(airflow_transport(f'{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "none"}}}}') + LEGACY_CONFIG_FILE)

    assert check(entry, "openlineage_transport") is None
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in env_var_names(entry)


def test_a_composite_airflow_transport_the_legacy_config_file_could_extend_cant_be_verified():
    entry = entry_for(airflow_transport('{"type": "composite", "transports": {"console": {"type": "console"}}}') + LEGACY_CONFIG_FILE)

    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.WARN
    assert "OPENLINEAGE_CONFIG" in message


def test_openlineage_url_alone_cant_be_verified_with_a_legacy_config_file_that_could_set_a_transport():
    entry = entry_for(DOCS_RECIPE + LEGACY_CONFIG_FILE)

    assert check(entry, "openlineage_transport")[0] == FindingStatus.WARN


# api_key and apiKey both set: before 1.38.0 the client takes api_key whenever it's present;
# from 1.38.0, the first non-empty of apiKey, apikey, api_key.
EMPTY_API_KEY_ALIAS = airflow_transport(f'{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "good", "api_key": ""}}}}')
EMPTY_APIKEY_ALIAS = airflow_transport(f'{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "", "api_key": "good"}}}}')


def test_conflicting_api_key_aliases_follow_each_client_generation():
    assert entry_for(EMPTY_API_KEY_ALIAS, requirements=PROVIDER + "openlineage-python==1.37.0\n").already_configured is False
    assert entry_for(EMPTY_API_KEY_ALIAS, requirements=PROVIDER + "openlineage-python==1.38.0\n").already_configured is True
    unknown = entry_for(EMPTY_API_KEY_ALIAS)
    assert unknown.already_configured is False
    assert check(unknown, "openlineage_transport")[0] == FindingStatus.WARN


def test_aliases_both_generations_agree_on_count_without_a_known_client_version():
    for requirements in (PROVIDER, PROVIDER + "openlineage-python==1.24.2\n", PROVIDER + "openlineage-python==1.49.0\n"):
        assert entry_for(EMPTY_APIKEY_ALIAS, requirements=requirements).already_configured is True


@pytest.mark.parametrize(
    "fragment, named",
    [('{"url": "https://elsewhere.invalid"}', "https://elsewhere.invalid"), ('{"auth": {"type": "none"}}', "without an API key")],
    ids=["explicit-bad-url", "explicit-non-api-key-auth"],
)
def test_an_untyped_airflow_transport_fragment_no_config_file_could_fix_fails(fragment, named):
    """The file can supply the missing type, but never override the fragment's own URL or auth."""
    entry = entry_for(airflow_transport(fragment) + LEGACY_CONFIG_FILE)

    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in message
    assert named in message


# --- a transport aimed at a Datadog intake is corrected in place ---------------------

WRONG_SITE_TRANSPORT = (
    "#!/bin/sh\n"
    "export MY_TEAM_SETTING=keep-me\n"
    """export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.datadoghq.com", """
    """"timeout": 5, "auth": {"type": "api_key", "apiKey": "not-a-real-key"}}'\n"""
    "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
)


def transport_change(entry) -> EnvVarChange:
    return next(fc for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange) and fc.name == "AIRFLOW__OPENLINEAGE__TRANSPORT")


def test_a_transport_aimed_at_another_sites_intake_is_rewritten_in_place_not_failed():
    entry = entry_for(WRONG_SITE_TRANSPORT, airflow_version="2.8.1", constraints="apache-airflow-providers-openlineage==1.14.0\n")

    assert check(entry, "openlineage_transport") is None
    change = transport_change(entry)
    assert change.secret is True
    assert change.from_value is None  # the old JSON carries a key, so it's never copied into the plan
    # only the fields set -- apply merges them into the transport (timeout and all) as it is then
    assert json.loads(change.to_value) == {"url": INTAKE, "auth": {"type": "api_key", "apiKey": DD_API_KEY_PLACEHOLDER}}
    assert "not-a-real-key" not in json.dumps(asdict(entry))
    # it wins over OPENLINEAGE_URL, so neither OPENLINEAGE_URL nor OPENLINEAGE_API_KEY is proposed
    assert not env_var_names(entry) & {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"}


def test_the_rewritten_transport_is_written_over_its_own_line_and_then_counts_as_configured():
    entry = entry_for(WRONG_SITE_TRANSPORT, airflow_version="2.8.1")
    changes = [
        replace(fc, to_value=merge_transport_fields(WRONG_SITE_TRANSPORT, fc.to_value)) if fc.name == "AIRFLOW__OPENLINEAGE__TRANSPORT" else fc
        for fc in entry.plan.file_changes
        if isinstance(fc, EnvVarChange)
    ]

    written = interpolate_api_key(patch_env_vars(WRONG_SITE_TRANSPORT, changes), "0123456789abcdef")

    lines = written.splitlines()
    assert lines[1] == "export MY_TEAM_SETTING=keep-me"
    assert lines[2].startswith("export AIRFLOW__OPENLINEAGE__TRANSPORT='{") and INTAKE in lines[2]
    assert '"timeout": 5' in lines[2]
    assert lines[3] == "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com"
    rescanned = analyze("2.8.1", PROVIDER, written, {}, SITE)
    assert rescanned.configured is True
    assert rescanned.issues == []


def test_an_intake_transport_on_the_right_site_without_an_api_key_is_rewritten():
    entry = entry_for(airflow_transport(f'{{"type": "http", "url": "{INTAKE}"}}') + NAMESPACE)

    assert check(entry, "openlineage_transport") is None
    assert json.loads(transport_change(entry).to_value)["auth"] == {"type": "api_key", "apiKey": DD_API_KEY_PLACEHOLDER}


def test_a_datadog_bound_transport_in_airflow_configuration_options_fails_since_apply_cant_rewrite_it():
    config_options = {"openlineage.transport": '{"type": "http", "url": "https://data-obs-intake.datadoghq.com"}'}

    entry = entry_for(DOCS_RECIPE, config_options=config_options)

    status, message = check(entry, "openlineage_transport")
    assert status == FindingStatus.FAIL
    assert "can't correct it in place" in message
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" not in env_var_names(entry)


def test_a_transport_assigned_twice_in_the_startup_script_is_never_rewritten():
    once = airflow_transport('{"type": "http", "url": "https://data-obs-intake.datadoghq.com"}')

    entry = entry_for(once + once + NAMESPACE)

    assert check(entry, "openlineage_transport")[0] == FindingStatus.FAIL
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" not in env_var_names(entry)


@pytest.mark.parametrize(
    "line",
    [
        """export AIRFLOW__OPENLINEAGE__TRANSPORT="{\\"type\\": \\"http\\", \\"url\\": \\"https://data-obs-intake.datadoghq.com\\"}"; export MY_TEAM_SETTING=keep-me""",
        """export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.datadoghq.com"}' && echo configured""",
        """export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.datadoghq.com"}' # set by ops""",
        """echo hi; export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.datadoghq.com"}'""",
    ],
    ids=["another-export-after", "command-after", "comment-after", "command-before"],
)
def test_a_transport_export_sharing_its_line_with_anything_else_is_never_rewritten(line):
    """patch_env_vars replaces the whole physical line, so anything else on it would be lost."""
    entry = entry_for(line + "\n" + NAMESPACE)

    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" not in env_var_names(entry)
    assert check(entry, "openlineage_transport")[0] in (FindingStatus.FAIL, FindingStatus.WARN)  # WARN: can't tell statically


def test_a_transport_to_a_non_datadog_backend_fails_with_a_plain_message_and_is_left_alone():
    entry = entry_for(airflow_transport('{"type": "http", "url": "https://marquez.example.com"}') + NAMESPACE)

    failure = next(i for i in entry.issues if i.check_id == "openlineage_transport")
    assert failure.status == FindingStatus.FAIL
    assert failure.message == (
        "AIRFLOW__OPENLINEAGE__TRANSPORT sends OpenLineage events to https://marquez.example.com, not to Datadog, "
        "and takes precedence over OPENLINEAGE_URL"
    )
    assert "left alone" in failure.detail
    assert env_var_names(entry) == set()


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://data-obs-intake.datadoghq.com", True),
        ("https://data-obs-intake.us5.datadoghq.com", True),
        ("https://data-obs-intake.datadoghq.eu", True),
        ("https://data-obs-intake.ddog-gov.com", True),
        ("https://data-obs-intake.datad0g.com/api/v1/lineage", True),
        ("https://data-obs-intake.datadoghq.com.example.com", False),
        ("https://intake.datadoghq.com", False),
        ("https://marquez.example.com", False),
        (None, False),
    ],
)
def test_is_any_datadog_intake_url(url, expected):
    assert is_any_datadog_intake_url(url) is expected


# --- an existing literal API key that's known not to work is replaced -----------------

KEY = "0123456789abcdef0123456789abcdef"  # synthetic, shaped like a Datadog API key


def literal_key_recipe(url: str = INTAKE, key: str = KEY) -> str:
    return f"#!/bin/sh\nexport OPENLINEAGE_URL={url}\nexport OPENLINEAGE_API_KEY={key}\n" + NAMESPACE


def api_key_change(entry) -> "EnvVarChange | None":
    return next((fc for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange) and fc.name == "OPENLINEAGE_API_KEY"), None)


def never_called(dd_site, api_key):
    raise AssertionError("the intake must not be asked")


def test_a_literal_key_next_to_another_sites_url_is_replaced_along_with_the_site_without_asking_the_intake():
    entry = entry_for(literal_key_recipe(url="https://data-obs-intake.datadoghq.com"), validate_api_key=never_called)

    assert "OPENLINEAGE_URL" in env_var_names(entry)
    change = api_key_change(entry)
    assert (change.from_value, change.to_value, change.secret) == (None, DD_API_KEY_PLACEHOLDER, True)
    status, message = check(entry, "openlineage_api_key")
    assert status == FindingStatus.WARN
    assert "another Datadog site" in message
    assert KEY not in json.dumps(asdict(entry))


def test_a_literal_key_the_intake_rejects_is_replaced_with_a_warning():
    asked = []
    entry = entry_for(literal_key_recipe(), validate_api_key=lambda site, key: asked.append((site, key)) or False)

    assert asked == [(SITE, KEY)]
    assert api_key_change(entry).to_value == DD_API_KEY_PLACEHOLDER
    assert env_var_names(entry) == {"OPENLINEAGE_API_KEY"}  # the URL is already right
    assert check(entry, "openlineage_api_key") == (
        FindingStatus.WARN,
        "the existing OPENLINEAGE_API_KEY was rejected by Datadog; the plan replaces it with the selected API key",
    )
    assert entry.already_configured is False
    assert KEY not in json.dumps(asdict(entry))


def test_a_literal_key_the_intake_accepts_is_kept():
    entry = entry_for(literal_key_recipe(), validate_api_key=lambda site, key: True)

    assert api_key_change(entry) is None
    assert check(entry, "openlineage_api_key") is None
    assert entry.already_configured is True


@pytest.mark.parametrize(
    "value",
    ["$(aws secretsmanager get-secret-value --secret-id dd --query SecretString --output text)", "${DD_API_KEY}", "not-a-datadog-key"],
    ids=["command", "variable", "not-key-shaped"],
)
def test_a_key_that_isnt_a_literal_datadog_key_is_kept_and_never_checked(value):
    entry = entry_for(literal_key_recipe(key=value), validate_api_key=never_called)

    assert api_key_change(entry) is None
    assert check(entry, "openlineage_api_key") is None


def test_a_literal_key_that_cant_be_checked_offline_is_kept_with_a_warning():
    entry = entry_for(literal_key_recipe(), validate_api_key=None)

    assert api_key_change(entry) is None
    status, message = check(entry, "openlineage_api_key")
    assert status == FindingStatus.WARN
    assert message == "couldn't verify the existing OPENLINEAGE_API_KEY with Datadog, so it's kept"
    assert entry.already_configured is True


def test_a_literal_key_in_a_working_datadog_transport_that_the_intake_rejects_is_replaced_in_place():
    startup = airflow_transport(f'{{"type": "http", "url": "{INTAKE}", "auth": {{"type": "api_key", "apiKey": "{KEY}"}}}}')

    entry = entry_for(startup, validate_api_key=lambda site, key: False)

    assert json.loads(transport_change(entry).to_value) == {"url": INTAKE, "auth": {"type": "api_key", "apiKey": DD_API_KEY_PLACEHOLDER}}
    assert "API key in AIRFLOW__OPENLINEAGE__TRANSPORT was rejected" in check(entry, "openlineage_api_key")[1]
    assert KEY not in json.dumps(asdict(entry))


def test_a_replaced_key_is_written_over_its_own_line():
    startup = literal_key_recipe()
    entry = entry_for(startup, validate_api_key=lambda site, key: False)

    written = interpolate_api_key(patch_env_vars(startup, [api_key_change(entry)]), "fedcba9876543210fedcba9876543210")

    assert "export OPENLINEAGE_API_KEY=fedcba9876543210fedcba9876543210" in written
    assert KEY not in written


NEW_KEY = "fedcba9876543210fedcba9876543210"


def apply_env_var_changes(startup: str, entry) -> str:
    return interpolate_api_key(patch_env_vars(startup, [fc for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)]), NEW_KEY)


@pytest.mark.parametrize(
    "key_line",
    [
        f"export OPENLINEAGE_API_KEY={KEY}      # existing key",
        f'export OPENLINEAGE_API_KEY="{KEY}" # existing key',
        f"export OPENLINEAGE_API_KEY='{KEY}'  # existing key",
    ],
    ids=["unquoted", "double-quoted", "single-quoted"],
)
def test_a_commented_literal_key_the_intake_rejects_is_replaced_and_its_comment_kept(key_line):
    startup = f"#!/bin/sh\nexport MY_TEAM_SETTING=keep-me\nexport OPENLINEAGE_URL={INTAKE}\n{key_line}\n" + NAMESPACE
    asked = []
    entry = entry_for(startup, validate_api_key=lambda site, key: asked.append(key) or False)

    assert asked == [KEY]
    assert api_key_change(entry) is not None
    written = apply_env_var_changes(startup, entry)
    (key_line_now,) = [line for line in written.splitlines() if "OPENLINEAGE_API_KEY=" in line]
    assert key_line_now.startswith(f"export OPENLINEAGE_API_KEY={NEW_KEY} ") and key_line_now.endswith("# existing key")
    assert "export MY_TEAM_SETTING=keep-me" in written
    rescanned = analyze("2.10.3", PROVIDER, written, {}, SITE)
    assert rescanned.environment["OPENLINEAGE_API_KEY"] == NEW_KEY


def test_the_pms_commented_wrong_site_recipe_replaces_url_and_key_without_asking_the_intake():
    startup = (
        "#!/bin/sh\n"
        "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com      # wrong site\n"
        f"export OPENLINEAGE_API_KEY={KEY}        # stale key\n" + NAMESPACE
    )
    entry = entry_for(startup, validate_api_key=never_called)

    assert {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"} <= env_var_names(entry)
    written = apply_env_var_changes(startup, entry)
    assert f"export OPENLINEAGE_URL={INTAKE}      # wrong site" in written
    assert f"export OPENLINEAGE_API_KEY={NEW_KEY}        # stale key" in written
    assert analyze("2.10.3", PROVIDER, written, {}, SITE).configured is True


def test_a_rejected_key_assigned_twice_is_never_claimed_replaced():
    startup = literal_key_recipe() + f"export OPENLINEAGE_API_KEY={KEY}\n"
    entry = entry_for(startup, validate_api_key=lambda site, key: False)

    assert api_key_change(entry) is None
    status, message = check(entry, "openlineage_api_key")
    assert status == FindingStatus.WARN
    assert message == "the existing OPENLINEAGE_API_KEY was rejected by Datadog, and it's set in a way the plan can't safely edit"
    assert entry.already_configured is False


@pytest.mark.parametrize(
    "assignment",
    [f"MY_KEY={KEY}\nexport OPENLINEAGE_API_KEY=$MY_KEY", f'MY_KEY={KEY}\nexport OPENLINEAGE_API_KEY="${{MY_KEY}}"', f"export OPENLINEAGE_API_KEY={KEY}\nexport OPENLINEAGE_API_KEY=$OPENLINEAGE_API_KEY"],
    ids=["variable", "braced-variable", "re-exported-through-itself"],
)
def test_a_key_that_resolves_through_a_variable_is_never_checked_or_edited(assignment):
    startup = f"#!/bin/sh\nexport OPENLINEAGE_URL={INTAKE}\n{assignment}\n" + NAMESPACE
    entry = entry_for(startup, validate_api_key=never_called)

    assert api_key_change(entry) is None
    assert check(entry, "openlineage_api_key") is None


def test_a_comment_after_a_single_quoted_value_isnt_part_of_it():
    assert analyze("2.10.3", PROVIDER, f"export OPENLINEAGE_API_KEY='{KEY}'  # existing key\n", {}, SITE).environment["OPENLINEAGE_API_KEY"] == KEY


# --- env_tag: the namespace events carry, when it's statically known -------------------


@pytest.mark.parametrize(
    "startup, config_options, expected",
    [
        (DOCS_RECIPE.replace(NAMESPACE, ""), None, "my-env"),  # the plan writes ${AIRFLOW_ENV_NAME}
        (DOCS_RECIPE, None, "my-env"),  # export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}
        (DOCS_RECIPE.replace(NAMESPACE, 'export AIRFLOW__OPENLINEAGE__NAMESPACE="${AIRFLOW_ENV_NAME}"\n'), None, "my-env"),
        (DOCS_RECIPE.replace(NAMESPACE, "export AIRFLOW__OPENLINEAGE__NAMESPACE=$AIRFLOW_ENV_NAME\n"), None, "my-env"),
        (DOCS_RECIPE.replace(NAMESPACE, 'export AIRFLOW__OPENLINEAGE__NAMESPACE="${AIRFLOW_ENV_NAME}-eu"\n'), None, "my-env-eu"),
        (DOCS_RECIPE.replace(NAMESPACE, "export AIRFLOW__OPENLINEAGE__NAMESPACE=production\n"), None, "production"),
        (DOCS_RECIPE.replace(NAMESPACE, "export AIRFLOW__OPENLINEAGE__NAMESPACE=$(cat /tmp/ns)\n"), None, None),
        (DOCS_RECIPE.replace(NAMESPACE, "export AIRFLOW__OPENLINEAGE__NAMESPACE=$TEAM_NAMESPACE\n"), None, None),
        (DOCS_RECIPE.replace(NAMESPACE, "TEAM_NAMESPACE=production\nexport AIRFLOW__OPENLINEAGE__NAMESPACE=$TEAM_NAMESPACE\n"), None, None),
        (DOCS_RECIPE.replace(NAMESPACE, "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAMESPACE}\n"), None, None),
        (DOCS_RECIPE.replace(NAMESPACE, ""), {"openlineage.namespace": "analytics"}, "analytics"),
        (DOCS_RECIPE.replace(NAMESPACE, ""), {"openlineage.namespace": "${TEAM}"}, None),
        (DOCS_RECIPE, {"openlineage.namespace": "analytics"}, "my-env"),  # startup.sh's export wins
    ],
    ids=[
        "planned",
        "existing-braced",
        "existing-quoted",
        "existing-bare",
        "existing-derived",
        "existing-literal",
        "command",
        "other-variable",
        "other-variable-the-script-sets",
        "lookalike-variable",
        "config-option-literal",
        "config-option-non-literal",
        "startup-over-config-option",
    ],
)
def test_env_tag(startup, config_options, expected):
    assert entry_for(startup, config_options=config_options).env_tag == expected


def test_env_tag_is_the_providers_default_when_nothing_sets_a_namespace_and_the_plan_cant_write_one():
    startup = DOCS_RECIPE.replace(NAMESPACE, "")
    ctx = ProbeContext(environment={"Name": "my-env"}, requirements_text="", constraints_text=None, startup_script_text=startup, client=None)

    assert _env_tag(ctx, replace(entry_for(startup).plan, file_changes=[])) == "default"
