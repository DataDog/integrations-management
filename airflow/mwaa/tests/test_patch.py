# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.patch import ensure_constraint_line, patch_pins
from mwaa.plan import PinDiff


def test_patch_pins_rewrites_existing_line_in_place():
    text = (
        "# a comment\n"
        "apache-airflow-providers-openlineage==1.4.0\n"
        "apache-airflow-providers-snowflake==5.2.1\n"
    )
    diffs = [PinDiff("apache-airflow-providers-openlineage", "1.4.0", "1.14.0")]

    patched = patch_pins(text, diffs)

    lines = patched.splitlines()
    assert lines[0] == "# a comment"
    assert lines[1] == "apache-airflow-providers-openlineage==1.14.0"
    assert lines[2] == "apache-airflow-providers-snowflake==5.2.1"  # untouched


def test_patch_pins_preserves_indentation_and_trailing_content():
    text = "  apache-airflow-providers-openlineage==1.4.0  # pinned\n"
    diffs = [PinDiff("apache-airflow-providers-openlineage", "1.4.0", "1.14.0")]

    patched = patch_pins(text, diffs)

    assert patched == "  apache-airflow-providers-openlineage==1.14.0  # pinned\n"


def test_patch_pins_appends_packages_with_no_existing_line():
    text = "apache-airflow-providers-openlineage==1.4.0\n"
    diffs = [
        PinDiff("apache-airflow-providers-openlineage", "1.4.0", "1.14.0"),
        PinDiff("apache-airflow-providers-common-compat", None, "1.2.1"),
    ]

    patched = patch_pins(text, diffs)

    assert patched == (
        "apache-airflow-providers-openlineage==1.14.0\n"
        "apache-airflow-providers-common-compat==1.2.1\n"
    )
    assert "#" not in patched  # no marker/explanatory comment added


def test_patch_pins_adds_bare_package_name_for_unpinned_target():
    diffs = [PinDiff("apache-airflow-providers-openlineage", None, "unpinned (resolved by MWAA's current default constraints)")]

    patched = patch_pins("pandas==2.1.4\n", diffs)

    assert "apache-airflow-providers-openlineage\n" in patched
    assert "apache-airflow-providers-openlineage==" not in patched


def test_patch_pins_does_not_touch_unrelated_packages():
    text = "pandas==2.1.4\nboto3==1.34.11\n"
    patched = patch_pins(text, [PinDiff("apache-airflow-providers-openlineage", None, "1.14.0")])

    assert "pandas==2.1.4" in patched
    assert "boto3==1.34.11" in patched


def test_ensure_constraint_line_prepends_when_missing():
    result = ensure_constraint_line("pandas==2.1.4\n", "/usr/local/airflow/dags/constraints.txt")
    assert result.startswith('--constraint "/usr/local/airflow/dags/constraints.txt"\n')
    assert "pandas==2.1.4" in result


def test_ensure_constraint_line_leaves_existing_line_untouched():
    text = '--constraint "/usr/local/airflow/dags/constraints.txt"\npandas==2.1.4\n'
    assert ensure_constraint_line(text, "/usr/local/airflow/dags/constraints.txt") == text
