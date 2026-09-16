# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.startup_script import render_startup_script, startup_script_looks_configured


def test_render_startup_script_includes_config_path_workaround_for_2_8_1():
    script = render_startup_script("2.8.1", "datadoghq.com", "fake-dd-api-key", "my-mwaa-prod")
    assert 'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""' in script
    assert "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com" in script
    assert "export OPENLINEAGE_API_KEY=fake-dd-api-key" in script


def test_render_startup_script_omits_workaround_for_newer_versions():
    script = render_startup_script("2.10.1", "datadoghq.com", "fake-dd-api-key", "my-mwaa-prod")
    assert "CONFIG_PATH" not in script
    assert "DISABLED_FOR_OPERATORS" not in script


def test_render_startup_script_interpolates_the_real_environment_name():
    script = render_startup_script("2.10.1", "datadoghq.com", "fake-dd-api-key", "my-mwaa-prod")
    assert 'export AIRFLOW_ENV_NAME="my-mwaa-prod"' in script
    # Kept, not hardcoded away -- see the module docstring for why.
    assert "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}" in script
    lines = script.splitlines()
    assert lines.index('export AIRFLOW_ENV_NAME="my-mwaa-prod"') < lines.index(
        "export AIRFLOW__OPENLINEAGE__NAMESPACE=${AIRFLOW_ENV_NAME}"
    )


def test_startup_script_looks_configured_true_when_url_present():
    assert startup_script_looks_configured("export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n") is True


def test_startup_script_looks_configured_false_when_missing():
    assert startup_script_looks_configured("echo hello\n") is False
    assert startup_script_looks_configured(None) is False


def test_startup_script_looks_configured_recognizes_transport_json_mechanism():
    script = "export AIRFLOW__OPENLINEAGE__TRANSPORT='{\"type\": \"http\", \"url\": \"https://x.invalid\"}'\n"
    assert startup_script_looks_configured(script) is True
