# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import asdict

from mwaa.plan import ConstraintDirectiveAdded, EnvVarChange, PinChange, compute_plan, plan_from_dict
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER


def test_flagged_version_with_stale_pins_needs_upgrade():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.4.0\napache-airflow-providers-common-sql==1.10.0\n",
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert plan.upgrade_needed is True
    assert plan.source == "flagged_version_table"
    assert plan.matched_table_entry.airflow_version == "2.8.1"

    pin_changes = [fc for fc in plan.file_changes if isinstance(fc, PinChange)]
    constraint_pins = [c for c in pin_changes if c.path == "dags/constraints.txt"]
    requirements_pins = [c for c in pin_changes if c.path == "requirements.txt"]
    assert constraint_pins  # constraints.txt gets pin changes
    assert requirements_pins  # requirements.txt gets the same pin changes

    ol_diff = next(c for c in constraint_pins if c.package == "apache-airflow-providers-openlineage")
    assert ol_diff.from_version == "1.4.0"
    assert ol_diff.to_version == "1.14.0"

    # common-compat has no current pin at all -- should show as an addition (from_version None).
    compat_diff = next(c for c in constraint_pins if c.package == "apache-airflow-providers-common-compat")
    assert compat_diff.from_version is None
    assert compat_diff.to_version == "1.2.1"

    assert any(isinstance(fc, ConstraintDirectiveAdded) for fc in plan.file_changes)
    assert any(isinstance(fc, EnvVarChange) for fc in plan.file_changes)  # no startup.sh at all yet


def test_flagged_version_already_upgraded_needs_no_package_or_directive_changes():
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
        startup_script_text=(
            "#!/bin/sh\n"
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
            'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""\n'
            'export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
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
        environment_name="my-env",
    )
    assert plan.upgrade_needed is True
    assert plan.source == "unflagged_version"
    assert plan.matched_table_entry is None

    paths = {fc.path for fc in plan.file_changes if isinstance(fc, (PinChange, ConstraintDirectiveAdded))}
    assert "dags/constraints.txt" not in paths
    assert "requirements.txt" in paths
    assert any(isinstance(fc, EnvVarChange) for fc in plan.file_changes)


def test_unflagged_version_with_provider_already_pinned_and_startup_configured_needs_no_upgrade():
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="apache-airflow-providers-openlineage==2.8.0\n",
        constraints_text=None,
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
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
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert plan.upgrade_needed is False
    assert plan.file_changes == []


def test_requirements_txt_gets_constraint_directive_when_missing():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        constraints_text="apache-airflow-providers-openlineage==1.4.0\n",
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    directive = next(fc for fc in plan.file_changes if isinstance(fc, ConstraintDirectiveAdded))
    assert directive.path == "requirements.txt"
    assert directive.line == '--constraint "/usr/local/airflow/dags/constraints.txt"'


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
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
            'export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""\n'
            'export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert plan.file_changes == []


# --- startup.sh env var diffing ------------------------------------------------


def test_env_var_change_proposed_when_url_points_at_the_wrong_site():
    plan = compute_plan(
        airflow_version="3.0.6",
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text=None,
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datad0g.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",  # customer's real site differs from what's exported
        environment_name="my-env",
    )
    env_changes = [fc for fc in plan.file_changes if isinstance(fc, EnvVarChange)]
    assert len(env_changes) == 1
    change = env_changes[0]
    assert change.name == "OPENLINEAGE_URL"
    assert change.from_value == "https://data-obs-intake.datad0g.com"
    assert change.to_value == "https://data-obs-intake.datadoghq.com"
    assert change.secret is False


def test_env_var_change_never_proposed_for_a_secret_that_already_has_a_value():
    """Can't verify a real key against DD_API_KEY_PLACEHOLDER, so presence alone is enough."""
    plan = compute_plan(
        airflow_version="3.0.6",
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text=None,
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key-that-might-even-be-wrong\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert not any(isinstance(fc, EnvVarChange) and fc.name == "OPENLINEAGE_API_KEY" for fc in plan.file_changes)


def test_env_var_change_proposed_for_a_missing_secret_variable():
    plan = compute_plan(
        airflow_version="3.0.6",
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        constraints_text=None,
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    change = next(fc for fc in plan.file_changes if isinstance(fc, EnvVarChange) and fc.name == "OPENLINEAGE_API_KEY")
    assert change.from_value is None
    assert change.to_value == DD_API_KEY_PLACEHOLDER
    assert change.secret is True


# --- serialization --------------------------------------------------------------


def test_plan_from_dict_round_trips_every_file_change_variant():
    # matched_table_entry deliberately None here -- a flagged version's
    # FlaggedVersionEntry.wheel_only_packages round-trips as a list (asdict
    # turns the tuple into one), which would fail a strict == even though the
    # content is identical. See test_session.py for that shape.
    from mwaa.plan import Plan

    plan = Plan(
        upgrade_needed=True,
        rationale="test",
        source="unflagged_version",
        matched_table_entry=None,
        source_doc="https://example.invalid",
        file_changes=[
            PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version="1.4.0", to_version="1.14.0"),
            ConstraintDirectiveAdded(path="requirements.txt", line='--constraint "/usr/local/airflow/dags/constraints.txt"'),
            EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_API_KEY", from_value=None, to_value=DD_API_KEY_PLACEHOLDER, secret=True),
        ],
    )

    loaded = plan_from_dict(asdict(plan))

    assert loaded == plan
