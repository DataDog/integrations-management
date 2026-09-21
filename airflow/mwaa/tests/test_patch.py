# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.patch import ensure_constraint_line, patch_env_vars, patch_pins
from mwaa.plan import EnvVarChange, PinChange
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER


def test_patch_pins_rewrites_existing_line_in_place():
    text = (
        "# a comment\n"
        "apache-airflow-providers-openlineage==1.4.0\n"
        "apache-airflow-providers-snowflake==5.2.1\n"
    )
    changes = [PinChange(path="dags/constraints.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0")]

    patched = patch_pins(text, changes)

    lines = patched.splitlines()
    assert lines[0] == "# a comment"
    assert lines[1] == "apache-airflow-providers-openlineage==1.14.0"
    assert lines[2] == "apache-airflow-providers-snowflake==5.2.1"  # untouched


def test_patch_pins_preserves_indentation_and_trailing_content():
    text = "  apache-airflow-providers-openlineage==1.4.0  # pinned\n"
    changes = [PinChange(path="dags/constraints.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0")]

    patched = patch_pins(text, changes)

    assert patched == "  apache-airflow-providers-openlineage==1.14.0  # pinned\n"


def test_patch_pins_appends_packages_with_no_existing_line():
    text = "apache-airflow-providers-openlineage==1.4.0\n"
    changes = [
        PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0"),
        PinChange(path="requirements.txt", package="apache-airflow-providers-common-compat", from_version=None, to_version="1.2.1"),
    ]

    patched = patch_pins(text, changes)

    assert patched == (
        "apache-airflow-providers-openlineage==1.14.0\n"
        "apache-airflow-providers-common-compat==1.2.1\n"
    )
    assert "#" not in patched  # no marker/explanatory comment added


def test_patch_pins_adds_bare_package_name_for_unpinned_target():
    changes = [
        PinChange(
            path="requirements.txt",
            package="apache-airflow-providers-openlineage",
            from_version=None,
            to_version="unpinned (resolved by MWAA's current default constraints)",
        )
    ]

    patched = patch_pins("pandas==2.1.4\n", changes)

    assert "apache-airflow-providers-openlineage\n" in patched
    assert "apache-airflow-providers-openlineage==" not in patched


def test_patch_pins_does_not_touch_unrelated_packages():
    text = "pandas==2.1.4\nboto3==1.34.11\n"
    patched = patch_pins(text, [PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version=None, to_version="1.14.0")])

    assert "pandas==2.1.4" in patched
    assert "boto3==1.34.11" in patched


def test_ensure_constraint_line_prepends_when_missing():
    result = ensure_constraint_line("pandas==2.1.4\n", "/usr/local/airflow/dags/constraints.txt")
    assert result.startswith('--constraint "/usr/local/airflow/dags/constraints.txt"\n')
    assert "pandas==2.1.4" in result


def test_ensure_constraint_line_leaves_existing_line_untouched():
    text = '--constraint "/usr/local/airflow/dags/constraints.txt"\npandas==2.1.4\n'
    assert ensure_constraint_line(text, "/usr/local/airflow/dags/constraints.txt") == text


# --- patch_env_vars ------------------------------------------------------------


def test_patch_env_vars_appends_to_a_brand_new_script():
    change = EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_URL", from_value=None, to_value="https://data-obs-intake.datadoghq.com", secret=False)

    patched = patch_env_vars(None, [change])

    assert patched == "#!/bin/sh\nexport OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"


def test_patch_env_vars_replaces_an_existing_line_in_place():
    text = "#!/bin/sh\nexport SOME_OTHER_VAR=1\nexport OPENLINEAGE_URL=https://data-obs-intake.datad0g.com\n"
    change = EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_URL", from_value="https://data-obs-intake.datad0g.com", to_value="https://data-obs-intake.datadoghq.com", secret=False)

    patched = patch_env_vars(text, [change])

    lines = patched.splitlines()
    assert lines[1] == "export SOME_OTHER_VAR=1"  # untouched -- the whole point
    assert lines[2] == "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com"


def test_patch_env_vars_preserves_unrelated_existing_content():
    text = "#!/bin/sh\necho 'custom setup'\nexport SOME_OTHER_VAR=keep-me\n"
    change = EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_URL", from_value=None, to_value="https://data-obs-intake.datadoghq.com", secret=False)

    patched = patch_env_vars(text, [change])

    assert "echo 'custom setup'" in patched
    assert "export SOME_OTHER_VAR=keep-me" in patched
    assert "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com" in patched


def test_patch_env_vars_writes_the_placeholder_for_a_secret_change():
    change = EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_API_KEY", from_value=None, to_value=DD_API_KEY_PLACEHOLDER, secret=True)

    patched = patch_env_vars("#!/bin/sh\n", [change])

    assert f"export OPENLINEAGE_API_KEY={DD_API_KEY_PLACEHOLDER}" in patched


def test_patch_env_vars_quotes_namespace_value():
    change = EnvVarChange(path="dags/startup.sh", name="AIRFLOW__OPENLINEAGE__NAMESPACE", from_value=None, to_value="my-env", secret=False)

    patched = patch_env_vars("#!/bin/sh\n", [change])

    assert 'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"' in patched
