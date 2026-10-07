# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.patch import patch_env_vars, patch_pins, patch_wheel_references, set_constraint_line
from mwaa.plan import EnvVarChange, PinChange, WheelReference
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
            to_version=None,
        )
    ]

    patched = patch_pins("pandas==2.1.4\n", changes)

    assert "apache-airflow-providers-openlineage\n" in patched
    assert "apache-airflow-providers-openlineage==" not in patched


def test_patch_pins_unpins_an_existing_pinned_line_for_a_none_target():
    changes = [PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version=None)]

    assert patch_pins("apache-airflow-providers-openlineage==1.4.0\n", changes) == "apache-airflow-providers-openlineage\n"


def test_patch_pins_replaces_an_underscore_spelled_line_with_one_canonical_line():
    """The real upstream constraints spell it openlineage_sql -- appending openlineage-sql
    alongside it would leave pip two conflicting constraints for one project."""
    text = "openlineage-python==1.3.1\nopenlineage_sql==1.3.1\npandas==2.1.4\n"
    changes = [PinChange(path="dags/constraints.txt", package="openlineage-sql", from_version="1.3.1", to_version="1.24.2")]

    assert patch_pins(text, changes) == "openlineage-python==1.3.1\nopenlineage-sql==1.24.2\npandas==2.1.4\n"


def test_patch_pins_leaves_exactly_one_line_when_a_project_is_pinned_under_two_spellings():
    text = "Apache_Airflow_Providers_OpenLineage==1.4.0\npandas==2.1.4\napache-airflow-providers-openlineage==1.4.0\n"
    changes = [PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0")]

    assert patch_pins(text, changes) == "apache-airflow-providers-openlineage==1.14.0\npandas==2.1.4\n"


def test_patch_pins_does_not_touch_unrelated_packages():
    text = "pandas==2.1.4\nboto3==1.34.11\n"
    patched = patch_pins(text, [PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version=None, to_version="1.14.0")])

    assert "pandas==2.1.4" in patched
    assert "boto3==1.34.11" in patched


def test_set_constraint_line_prepends_when_missing():
    result = set_constraint_line("pandas==2.1.4\n", '--constraint "/usr/local/airflow/dags/constraints.txt"')
    assert result == '--constraint "/usr/local/airflow/dags/constraints.txt"\npandas==2.1.4\n'


def test_set_constraint_line_replaces_an_existing_url_line_in_place():
    text = 'pandas==2.1.4\n--constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"\nboto3==1.34.11\n'

    result = set_constraint_line(text, '--constraint "/usr/local/airflow/dags/constraints.txt"')

    assert result == 'pandas==2.1.4\n--constraint "/usr/local/airflow/dags/constraints.txt"\nboto3==1.34.11\n'


def test_set_constraint_line_replaces_the_short_c_form_too():
    result = set_constraint_line("-c https://example.invalid/c.txt\npandas==2.1.4\n", '--constraint "/usr/local/airflow/dags/constraints.txt"')
    assert result == '--constraint "/usr/local/airflow/dags/constraints.txt"\npandas==2.1.4\n'


WHEEL = WheelReference(
    path="requirements.txt",
    package="apache-airflow-providers-openlineage",
    version="1.14.0",
    wheel_url="https://docs.datadoghq.com/resources/whl/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl",
    line="/usr/local/airflow/dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl",
)


def test_patch_wheel_references_replaces_the_packages_pin_line():
    text = "pandas==2.1.4\napache-airflow-providers-openlineage==1.1.0\nboto3==1.34.11\n"

    patched = patch_wheel_references(text, [WHEEL])

    assert patched == f"pandas==2.1.4\n{WHEEL.line}\nboto3==1.34.11\n"


def test_patch_wheel_references_replaces_a_different_wheel_for_the_same_package():
    text = "/usr/local/airflow/dags/apache_airflow_providers_openlineage-1.13.0-py3-none-any.whl\n"
    assert patch_wheel_references(text, [WHEEL]) == f"{WHEEL.line}\n"


def test_patch_wheel_references_replaces_an_underscore_spelled_pin():
    assert patch_wheel_references("Apache_Airflow_Providers_OpenLineage==1.1.0\n", [WHEEL]) == f"{WHEEL.line}\n"


def test_patch_wheel_references_appends_and_is_idempotent():
    once = patch_wheel_references("pandas==2.1.4\n", [WHEEL])

    assert once == f"pandas==2.1.4\n{WHEEL.line}\n"
    assert patch_wheel_references(once, [WHEEL]) == once


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


def test_patch_env_vars_rewrites_an_empty_namespace_line_in_place():
    text = '#!/bin/sh\nexport AIRFLOW__OPENLINEAGE__NAMESPACE=""\necho done\n'
    change = EnvVarChange(path="dags/startup.sh", name="AIRFLOW__OPENLINEAGE__NAMESPACE", from_value="", to_value="${AIRFLOW_ENV_NAME}", secret=False)

    patched = patch_env_vars(text, [change])

    assert patched == '#!/bin/sh\nexport AIRFLOW__OPENLINEAGE__NAMESPACE="${AIRFLOW_ENV_NAME}"\necho done\n'
