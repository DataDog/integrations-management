# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.plan import compute_plan


def test_flagged_version_with_stale_pins_needs_upgrade():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.4.0\napache-airflow-providers-common-sql==1.10.0\n",
        startup_script_text=None,
        dd_site="datadoghq.com",
    )
    assert plan.upgrade_needed is True
    assert plan.source == "flagged_version_table"
    assert plan.matched_table_entry.airflow_version == "2.8.1"

    paths = {fc.path for fc in plan.file_changes}
    assert "dags/constraints.txt" in paths
    assert "requirements.txt" in paths
    assert "dags/startup.sh" in paths

    constraints_change = next(fc for fc in plan.file_changes if fc.path == "dags/constraints.txt")
    ol_diff = next(d for d in constraints_change.pin_diff if d.package == "apache-airflow-providers-openlineage")
    assert ol_diff.from_version == "1.4.0"
    assert ol_diff.to_version == "1.14.0"

    # common-compat has no current pin at all -- should show as an addition (from_version None).
    compat_diff = next(d for d in constraints_change.pin_diff if d.package == "apache-airflow-providers-common-compat")
    assert compat_diff.from_version is None
    assert compat_diff.to_version == "1.2.1"


def test_flagged_version_already_upgraded_needs_no_package_changes():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text=(
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        constraints_text=(
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        dd_site="datadoghq.com",
    )
    assert plan.upgrade_needed is False
    assert plan.file_changes == []


def test_unflagged_version_without_provider_needs_addition_only():
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="pandas==2.1.4\n",
        constraints_text=None,
        startup_script_text=None,
        dd_site="datadoghq.com",
    )
    assert plan.upgrade_needed is True
    assert plan.source == "unflagged_version"
    assert plan.matched_table_entry is None

    paths = [fc.path for fc in plan.file_changes]
    assert "dags/constraints.txt" not in paths
    assert "requirements.txt" in paths
    assert "dags/startup.sh" in paths


def test_unflagged_version_with_provider_already_pinned_needs_no_upgrade():
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="apache-airflow-providers-openlineage==2.8.0\n",
        constraints_text=None,
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        dd_site="datadoghq.com",
    )
    assert plan.upgrade_needed is False
    assert plan.file_changes == []


def test_unflagged_version_recognizes_a_previously_added_bare_package_line():
    """apply's own output for this exact path (see patch.py's "unpinned" branch) is a bare
    `apache-airflow-providers-openlineage` line, no `==version` -- parse_pins alone can't see
    it, so without parse_bare_packages this would propose adding a duplicate on every re-scan."""
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="pandas==2.1.4\napache-airflow-providers-openlineage\n",
        constraints_text=None,
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        dd_site="datadoghq.com",
    )
    assert plan.upgrade_needed is False
    assert plan.file_changes == []


def test_requirements_txt_notes_missing_constraint_line():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.4.0\n",
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        dd_site="datadoghq.com",
    )
    requirements_change = next(fc for fc in plan.file_changes if fc.path == "requirements.txt")
    assert any("constraint" in note for note in requirements_change.notes)


def test_startup_script_change_omitted_when_already_configured():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text=(
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        constraints_text=(
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-sql==1.20.0\n"
            "apache-airflow-providers-common-compat==1.2.1\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        startup_script_text="export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n",
        dd_site="datadoghq.com",
    )
    assert plan.file_changes == []
