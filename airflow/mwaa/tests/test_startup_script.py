# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.startup_script import (
    DD_API_KEY_PLACEHOLDER,
    SECRET_VAR_NAMES,
    interpolate_api_key,
    parse_exports,
    render_export_line,
    target_values,
)


def test_target_values_includes_config_path_workaround_for_2_8_1():
    values = dict(target_values("2.8.1", "datadoghq.com", "my-mwaa-prod"))
    assert values["AIRFLOW__OPENLINEAGE__CONFIG_PATH"] == ""
    assert values["AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS"] == ""


def test_target_values_omits_workaround_for_newer_versions():
    values = dict(target_values("2.10.1", "datadoghq.com", "my-mwaa-prod"))
    assert "AIRFLOW__OPENLINEAGE__CONFIG_PATH" not in values
    assert "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS" not in values


def test_target_values_interpolates_the_real_environment_name():
    values = dict(target_values("2.10.1", "datadoghq.com", "my-mwaa-prod"))
    assert values["AIRFLOW__OPENLINEAGE__NAMESPACE"] == "my-mwaa-prod"


def test_target_values_never_carries_a_real_api_key():
    values = dict(target_values("2.10.1", "datadoghq.com", "my-mwaa-prod"))
    assert values["OPENLINEAGE_API_KEY"] == DD_API_KEY_PLACEHOLDER


def test_openlineage_api_key_is_the_only_secret_variable():
    assert SECRET_VAR_NAMES == frozenset({"OPENLINEAGE_API_KEY"})


def test_render_export_line_quotes_namespace_and_empty_values():
    assert render_export_line("AIRFLOW__OPENLINEAGE__NAMESPACE", "my-env") == 'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"'
    assert render_export_line("AIRFLOW__OPENLINEAGE__CONFIG_PATH", "") == 'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""'


def test_render_export_line_leaves_url_and_key_unquoted():
    assert render_export_line("OPENLINEAGE_URL", "https://data-obs-intake.datadoghq.com") == "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com"
    assert render_export_line("OPENLINEAGE_API_KEY", DD_API_KEY_PLACEHOLDER) == f"export OPENLINEAGE_API_KEY={DD_API_KEY_PLACEHOLDER}"


def test_interpolate_api_key_substitutes_the_placeholder():
    line = render_export_line("OPENLINEAGE_API_KEY", DD_API_KEY_PLACEHOLDER)
    real = interpolate_api_key(line, "real-dd-api-key")
    assert real == "export OPENLINEAGE_API_KEY=real-dd-api-key"
    assert DD_API_KEY_PLACEHOLDER not in real


def test_parse_exports_reads_back_quoted_and_unquoted_values():
    script = (
        "#!/bin/sh\n"
        "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
        'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
    )
    assert parse_exports(script) == {
        "OPENLINEAGE_URL": "https://data-obs-intake.datadoghq.com",
        "AIRFLOW__OPENLINEAGE__NAMESPACE": "my-env",
    }


def test_parse_exports_ignores_unrelated_lines():
    assert parse_exports("echo hello\nexport SOME_OTHER_VAR=1\n") == {}


def test_parse_exports_empty_for_empty_text():
    assert parse_exports("") == {}
