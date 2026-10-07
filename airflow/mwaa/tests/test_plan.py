# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from dataclasses import asdict

from mwaa.base_constraints import BaseConstraints
from mwaa.plan import ConstraintDirectiveChange, EnvVarChange, PinChange, WheelReference, compute_plan, plan_from_dict
from mwaa.startup_script import DD_API_KEY_PLACEHOLDER


def local_base(text: str) -> BaseConstraints:
    return BaseConstraints(source="s3://my-bucket/dags/constraints.txt", text=text)


def test_flagged_version_with_stale_pins_needs_upgrade():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        base_constraints=local_base("apache-airflow-providers-openlineage==1.4.0\napache-airflow-providers-common-sql==1.10.0\n"),
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

    assert any(isinstance(fc, ConstraintDirectiveChange) for fc in plan.file_changes)
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
        base_constraints=local_base(
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
        base_constraints=None,
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert plan.upgrade_needed is True
    assert plan.source == "unflagged_version"
    assert plan.matched_table_entry is None

    pin_changes = [fc for fc in plan.file_changes if isinstance(fc, (PinChange, ConstraintDirectiveChange))]
    assert pin_changes == [PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version=None, to_version=None)]
    assert any(isinstance(fc, EnvVarChange) for fc in plan.file_changes)


def test_unflagged_version_with_provider_already_pinned_and_startup_configured_needs_no_upgrade():
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="apache-airflow-providers-openlineage==2.8.0\n",
        base_constraints=None,
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
    """apply's own output for this exact path (see patch.py's to_version=None branch) is a bare
    `apache-airflow-providers-openlineage` line, no `==version` -- parse_pins alone can't see
    it, so without mentions_package this would propose adding a duplicate on every re-scan."""
    plan = compute_plan(
        airflow_version="2.10.1",
        requirements_text="pandas==2.1.4\napache-airflow-providers-openlineage\n",
        base_constraints=None,
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


def test_unflagged_version_with_only_common_sql_still_proposes_the_provider():
    """common-sql is a dependency of lots of providers, not a sign OpenLineage is installed."""
    plan = compute_plan(
        airflow_version="2.10.3",
        requirements_text="apache-airflow-providers-common-sql==1.20.0\n",
        base_constraints=None,
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    assert plan.upgrade_needed is True
    assert PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version=None, to_version=None) in plan.file_changes


def test_requirements_txt_gets_constraint_directive_when_missing():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        base_constraints=local_base("apache-airflow-providers-openlineage==1.4.0\n"),
        startup_script_text=(
            "export OPENLINEAGE_URL=https://data-obs-intake.datadoghq.com\n"
            "export OPENLINEAGE_API_KEY=some-real-key\n"
            'export AIRFLOW__OPENLINEAGE__NAMESPACE="my-env"\n'
        ),
        dd_site="datadoghq.com",
        environment_name="my-env",
    )
    directive = next(fc for fc in plan.file_changes if isinstance(fc, ConstraintDirectiveChange))
    assert directive.path == "requirements.txt"
    assert directive.from_line is None
    assert directive.to_line == '--constraint "/usr/local/airflow/dags/constraints.txt"'


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
        base_constraints=local_base(
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


UPSTREAM_URL = "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"
UPSTREAM_TEXT = (
    "apache-airflow-providers-amazon==8.16.0\n"
    "apache-airflow-providers-common-sql==1.10.0\n"
    "apache-airflow-providers-openlineage==1.4.0\n"
    "boto3==1.33.13\n"
)


def test_url_constraint_line_is_replaced_and_pins_are_diffed_against_that_file():
    url_line = f'--constraint "{UPSTREAM_URL}"'
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text=f"{url_line}\napache-airflow-providers-amazon==8.16.0\n",
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    directives = [fc for fc in plan.file_changes if isinstance(fc, ConstraintDirectiveChange)]
    assert directives == [
        ConstraintDirectiveChange(path="requirements.txt", from_line=url_line, to_line='--constraint "/usr/local/airflow/dags/constraints.txt"')
    ]
    constraint_pins = {fc.package: fc for fc in plan.file_changes if isinstance(fc, PinChange) and fc.path == "dags/constraints.txt"}
    assert constraint_pins["apache-airflow-providers-openlineage"].from_version == "1.4.0"
    assert constraint_pins["apache-airflow-providers-common-sql"].from_version == "1.10.0"
    assert constraint_pins["openlineage-python"].from_version is None  # upstream doesn't pin it at all
    assert UPSTREAM_URL in plan.rationale


def test_constraints_from_version_comes_from_the_base_file_not_requirements():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.6.0\n",
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=UPSTREAM_TEXT),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    ol_changes = {fc.path: fc for fc in plan.file_changes if isinstance(fc, PinChange) and fc.package == "apache-airflow-providers-openlineage"}
    assert ol_changes["dags/constraints.txt"].from_version == "1.4.0"
    assert ol_changes["requirements.txt"].from_version == "1.6.0"


def test_custom_named_local_constraints_file_is_patched_in_place_with_no_directive_change():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text='--constraint "/usr/local/airflow/dags/deps/my-constraints.txt"\napache-airflow-providers-openlineage==1.4.0\n',
        base_constraints=BaseConstraints(source="s3://my-bucket/dags/deps/my-constraints.txt", text=UPSTREAM_TEXT),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    assert not any(isinstance(fc, ConstraintDirectiveChange) for fc in plan.file_changes)
    assert any(isinstance(fc, PinChange) and fc.path == "dags/constraints.txt" for fc in plan.file_changes)


def test_unreadable_base_constraints_leaves_out_every_package_change():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="apache-airflow-providers-openlineage==1.4.0\n",
        base_constraints=BaseConstraints(source=UPSTREAM_URL, text=None, error="could not download it: timed out"),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    assert plan.upgrade_needed is True
    assert all(isinstance(fc, EnvVarChange) for fc in plan.file_changes)
    assert plan.file_changes  # startup.sh changes are still planned
    assert "timed out" in plan.rationale


def test_flagged_version_without_any_base_constraints_also_fails_safe():
    plan = compute_plan(
        airflow_version="2.8.1",
        requirements_text="",
        base_constraints=None,
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    assert all(isinstance(fc, EnvVarChange) for fc in plan.file_changes)


UPSTREAM_2_7_2_TEXT = "apache-airflow-providers-common-sql==1.7.2\napache-airflow-providers-openlineage==1.1.0\nboto3==1.28.62\n"
OPENLINEAGE_WHEEL = "apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl"
COMMON_COMPAT_WHEEL = "apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl"


def test_2_7_2_references_datadog_wheels_instead_of_pinning_those_packages():
    plan = compute_plan(
        airflow_version="2.7.2",
        requirements_text="apache-airflow-providers-openlineage==1.1.0\n",
        base_constraints=BaseConstraints(source="https://example.invalid/c.txt", text=UPSTREAM_2_7_2_TEXT),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    wheels = [fc for fc in plan.file_changes if isinstance(fc, WheelReference)]
    assert wheels == [
        WheelReference(
            path="requirements.txt",
            package="apache-airflow-providers-openlineage",
            version="1.14.0",
            wheel_url=f"https://docs.datadoghq.com/resources/whl/{OPENLINEAGE_WHEEL}",
            line=f"/usr/local/airflow/dags/{OPENLINEAGE_WHEEL}",
        ),
        WheelReference(
            path="requirements.txt",
            package="apache-airflow-providers-common-compat",
            version="1.2.2",
            wheel_url=f"https://docs.datadoghq.com/resources/whl/{COMMON_COMPAT_WHEEL}",
            line=f"/usr/local/airflow/dags/{COMMON_COMPAT_WHEEL}",
        ),
    ]
    requirements_pins = {fc.package for fc in plan.file_changes if isinstance(fc, PinChange) and fc.path == "requirements.txt"}
    assert requirements_pins == {"openlineage-integration-common", "openlineage-python", "openlineage-sql"}
    constraint_pins = {fc.package: fc.to_version for fc in plan.file_changes if isinstance(fc, PinChange) and fc.path == "dags/constraints.txt"}
    assert constraint_pins["apache-airflow-providers-openlineage"] == "1.14.0"  # constraints.txt still pins the wheel packages
    assert constraint_pins["apache-airflow-providers-common-compat"] == "1.2.2"


def test_2_7_2_recognizes_existing_wheel_references():
    plan = compute_plan(
        airflow_version="2.7.2",
        requirements_text=(
            '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
            f"/usr/local/airflow/dags/{OPENLINEAGE_WHEEL}\n"
            f"/usr/local/airflow/dags/{COMMON_COMPAT_WHEEL}\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        base_constraints=local_base(
            "apache-airflow-providers-openlineage==1.14.0\n"
            "apache-airflow-providers-common-compat==1.2.2\n"
            "openlineage-integration-common==1.24.2\n"
            "openlineage-python==1.24.2\n"
            "openlineage-sql==1.24.2\n"
        ),
        startup_script_text=None,
        dd_site="datadoghq.com",
        environment_name="my-env",
    )

    assert all(isinstance(fc, EnvVarChange) for fc in plan.file_changes)


# --- startup.sh env var diffing ------------------------------------------------


def test_env_var_change_proposed_when_url_points_at_the_wrong_site():
    plan = compute_plan(
        airflow_version="3.0.6",
        requirements_text="apache-airflow-providers-openlineage==2.18.0\n",
        base_constraints=None,
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
        base_constraints=None,
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
        base_constraints=None,
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
            PinChange(path="requirements.txt", package="apache-airflow-providers-openlineage", from_version=None, to_version=None),
            ConstraintDirectiveChange(path="requirements.txt", from_line=None, to_line='--constraint "/usr/local/airflow/dags/constraints.txt"'),
            ConstraintDirectiveChange(
                path="requirements.txt", from_line='--constraint "https://example.invalid/c.txt"', to_line='--constraint "/usr/local/airflow/dags/constraints.txt"'
            ),
            WheelReference(
                path="requirements.txt",
                package="apache-airflow-providers-common-compat",
                version="1.2.2",
                wheel_url=f"https://docs.datadoghq.com/resources/whl/{COMMON_COMPAT_WHEEL}",
                line=f"/usr/local/airflow/dags/{COMMON_COMPAT_WHEEL}",
            ),
            EnvVarChange(path="dags/startup.sh", name="OPENLINEAGE_API_KEY", from_value=None, to_value=DD_API_KEY_PLACEHOLDER, secret=True),
        ],
    )

    loaded = plan_from_dict(asdict(plan))

    assert loaded == plan
