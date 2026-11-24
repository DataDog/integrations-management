# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Five real MWAA environments the scan used to get wrong -- see real_environments/README.md."""

import json
from dataclasses import asdict
from pathlib import Path

from airflow_shared.reporter import FindingStatus
from mwaa.base_constraints import MINIMAL_CONSTRAINTS_HEADER
from mwaa.apply import apply_to_environment, check_files_unchanged, compute_apply_actions, interpolate_api_key
from mwaa.plan import ConstraintDirectiveChange, EnvVarChange, PinChange
from mwaa.probe import build_context
from mwaa.session import blocking_issues, build_session

from .conftest import FakeS3Client

FIXTURES = Path(__file__).parent / "real_environments"
SITE = "datad0g.com"
TRANSPORT_VARS = {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"}


def load(name: str) -> FakeS3Client:
    directory = FIXTURES / name
    environment = json.loads((directory / "environment.json").read_text())
    objects = {key: (directory / filename).read_text() for key, filename in json.loads((directory / "objects.json").read_text()).items()}
    client = FakeS3Client(environment, objects)
    for path_key, version_key in (("RequirementsS3Path", "RequirementsS3ObjectVersion"), ("StartupScriptS3Path", "StartupScriptS3ObjectVersion")):
        if environment.get(version_key) == "<latest>":
            client.environment[version_key] = client.versions[environment[path_key]]
    return client


def scan(client: FakeS3Client):
    ctx = build_context(client, client.environment["Name"])
    return ctx, build_session("s", "us-east-1", SITE, [ctx]).environments[0]


def issues(entry, status: FindingStatus) -> dict[str, str]:
    return {i.check_id: i.message for i in entry.issues if i.status == status}


def env_var_names(entry) -> set[str]:
    return {fc.name for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)}


def test_lakehouse_v3_is_configured_through_its_composite_default_http_transport():
    _, entry = scan(load("lakehouse-v3"))

    assert entry.already_configured is True
    assert env_var_names(entry) == set()
    assert "openlineage_transport" not in issues(entry, FindingStatus.FAIL) | issues(entry, FindingStatus.WARN)
    assert "openlineage_provider" not in issues(entry, FindingStatus.WARN)


def test_lakehouse_v2_with_the_provider_only_installed_by_its_startup_script_is_not_configured():
    _, entry = scan(load("lakehouse-v2"))

    assert entry.already_configured is False
    warnings = issues(entry, FindingStatus.WARN)
    assert set(warnings) == {"openlineage_provider"}  # no constraint_path noise on an unflagged version
    assert "startup script" in warnings["openlineage_provider"]
    assert not issues(entry, FindingStatus.FAIL)
    # the transport itself resolves to data-obs-intake.datad0g.com -- nothing to change there
    assert not env_var_names(entry) & TRANSPORT_VARS
    assert "AIRFLOW__OPENLINEAGE__NAMESPACE" not in env_var_names(entry)


def test_probe_281_whose_airflow_transport_overrides_openlineage_url_fails_and_proposes_no_transport_change():
    _, entry = scan(load("probe-281"))

    assert entry.already_configured is False
    failures = issues(entry, FindingStatus.FAIL)
    assert "openlineage_transport" in failures
    assert "AIRFLOW__OPENLINEAGE__TRANSPORT" in failures["openlineage_transport"]
    assert "https://startup-script-wins.invalid" in failures["openlineage_transport"]
    assert not env_var_names(entry) & TRANSPORT_VARS
    assert "AIRFLOW__OPENLINEAGE__NAMESPACE" not in env_var_names(entry)
    # requirements already carry the 2.8.1 targets under a local --constraint; the constraints file
    # still has upstream's openlineage_sql==1.7.0 next to the patched pin, which has to go, and
    # upstream's sqlparse==0.4.4, which common-sql 1.20.0 can't install against
    package_changes = [fc for fc in entry.plan.file_changes if not isinstance(fc, EnvVarChange)]
    assert package_changes == [
        PinChange(path="probe/281/dags/constraints.txt", package="openlineage-sql", from_version="1.7.0", to_version="1.24.2"),
        PinChange(path="probe/281/dags/constraints.txt", package="sqlparse", from_version="0.4.4", to_version="0.5.1"),
    ]
    assert "apache-airflow-providers-common-sql 1.20.0 needs sqlparse>=0.5.1" in entry.plan.rationale


def test_sandbox_281_writes_datadog_copies_next_to_its_orphaned_files():
    client = load("sandbox-281")
    ctx, entry = scan(client)

    assert entry.already_configured is False
    assert not issues(entry, FindingStatus.FAIL)
    assert "constraint_path" not in issues(entry, FindingStatus.WARN)  # the plan adds the --constraint line itself
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)} == {"probe/sandbox/dags/startup-datadog.sh"}
    assert env_var_names(entry) == {
        "OPENLINEAGE_URL",
        "OPENLINEAGE_API_KEY",
        "AIRFLOW__OPENLINEAGE__NAMESPACE",
        "AIRFLOW__OPENLINEAGE__CONFIG_PATH",
        "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS",
    }
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, PinChange)} == {
        "probe/sandbox/dags/constraints-datadog.txt",
        "probe/sandbox/requirements.txt",
    }
    assert entry.file_roles == {
        "probe/sandbox/dags/constraints-datadog.txt": "constraints",
        "probe/sandbox/requirements.txt": "requirements",
        "probe/sandbox/dags/startup-datadog.sh": "startup_script",
    }
    assert any(isinstance(fc, ConstraintDirectiveChange) for fc in entry.plan.file_changes)
    assert "dags/startup.sh already exists" in entry.plan.rationale
    assert "startup-datadog.sh" in entry.plan.rationale

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])

    assert client.objects["probe/sandbox/dags/startup.sh"] == (FIXTURES / "sandbox-281" / "someone-elses-startup.sh").read_text()
    assert "OPENLINEAGE_URL=https://data-obs-intake.datad0g.com" in client.objects["probe/sandbox/dags/startup-datadog.sh"]
    assert client.update_environment.call_args.kwargs["StartupScriptS3Path"] == "probe/sandbox/dags/startup-datadog.sh"
    # no --constraint line, so the constraints file pins only the OpenLineage packages: the
    # full upstream file's boto3==1.33.13 would make pip refuse this requirements.txt's boto3==1.34.11
    assert client.objects["probe/sandbox/dags/constraints-datadog.txt"] == MINIMAL_CONSTRAINTS_HEADER + (
        "apache-airflow-providers-openlineage==1.14.0\n"
        "apache-airflow-providers-common-sql==1.20.0\n"
        "apache-airflow-providers-common-compat==1.2.1\n"
        "openlineage-integration-common==1.24.2\n"
        "openlineage-python==1.24.2\n"
        "openlineage-sql==1.24.2\n"
    )
    assert client.objects["probe/sandbox/dags/constraints.txt"] == (FIXTURES / "sandbox-281" / "someone-elses-constraints.txt").read_text()
    assert client.objects["probe/sandbox/requirements.txt"].startswith('--constraint "/usr/local/airflow/dags/constraints-datadog.txt"\n')
    assert "boto3==1.34.11" in client.objects["probe/sandbox/requirements.txt"]


def test_blank_321_writes_requirements_datadog_txt_beside_an_existing_unconfigured_requirements_txt():
    client = load("blank-321")
    ctx, entry = scan(client)

    assert entry.already_configured is False
    assert not issues(entry, FindingStatus.FAIL)
    assert not issues(entry, FindingStatus.WARN)  # no --constraint line is fine on 3.2.1
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, PinChange)} == {"requirements-datadog.txt"}
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)} == {"dags/startup.sh"}
    assert "requirements-datadog.txt" in entry.plan.rationale

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])

    assert client.objects["requirements.txt"] == "pandas==2.1.4\n"
    assert client.objects["requirements-datadog.txt"] == "apache-airflow-providers-openlineage\n"
    kwargs = client.update_environment.call_args.kwargs
    assert kwargs["RequirementsS3Path"] == "requirements-datadog.txt"
    assert kwargs["StartupScriptS3Path"] == "dags/startup.sh"


def test_configured_281_on_the_upgrade_guides_packages_and_the_docs_recipe_is_configured():
    _, entry = scan(load("configured-281"))

    assert entry.already_configured is True
    assert entry.plan.file_changes == []
    assert not issues(entry, FindingStatus.FAIL)


def test_sandbox_281_referencing_a_missing_local_constraints_file_is_blocked_with_no_package_changes():
    client = load("sandbox-281")
    client.objects["probe/sandbox/requirements.txt"] = '--constraint "/usr/local/airflow/dags/my-constraints.txt"\n' + client.objects["probe/sandbox/requirements.txt"]
    _, entry = scan(client)

    failures = issues(entry, FindingStatus.FAIL)
    assert {"constraint_path", "base_constraints"} <= set(failures)
    assert blocking_issues(entry)
    assert not [fc for fc in entry.plan.file_changes if not isinstance(fc, EnvVarChange)]


def test_sandbox_281_with_a_constraint_path_outside_the_dags_mount_never_replaces_it_with_a_minimal_file():
    client = load("sandbox-281")
    client.objects["probe/sandbox/requirements.txt"] = '--constraint "/tmp/custom-constraints.txt"\n' + client.objects["probe/sandbox/requirements.txt"]
    _, entry = scan(client)

    assert "base_constraints" in issues(entry, FindingStatus.FAIL)
    assert blocking_issues(entry)
    assert not [fc for fc in entry.plan.file_changes if not isinstance(fc, EnvVarChange)]


TRANSPORT_STARTUP = "probe/transport/dags/startup-datadog.sh"


def test_transport_281_corrects_its_wrong_site_transport_in_its_real_startup_script():
    client = load("transport-281")
    ctx, entry = scan(client)

    assert not issues(entry, FindingStatus.FAIL)
    assert entry.already_configured is False
    assert env_var_names(entry) == {
        "AIRFLOW__OPENLINEAGE__TRANSPORT",
        "AIRFLOW__OPENLINEAGE__NAMESPACE",
        "AIRFLOW__OPENLINEAGE__CONFIG_PATH",
        "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS",
    }
    # every name in the payload is the environment's real file, not a generic label
    assert {fc.path for fc in entry.plan.file_changes} == {TRANSPORT_STARTUP}
    assert entry.file_roles == {TRANSPORT_STARTUP: "startup_script"}
    assert TRANSPORT_STARTUP in entry.file_versions and "dags/startup.sh" not in entry.file_versions
    assert "not-a-real-key" not in json.dumps(asdict(entry))

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    uploads = interpolate_api_key(compute_apply_actions(ctx, entry.plan), "0123456789abcdef")
    apply_to_environment(client, ctx, uploads, [])

    written = client.objects[TRANSPORT_STARTUP].splitlines()
    assert written[1] == "export MY_TEAM_SETTING=keep-me"
    assert '"url": "https://data-obs-intake.datad0g.com"' in written[2] and '"apiKey": "0123456789abcdef"' in written[2]
    assert client.update_environment.call_args.kwargs["StartupScriptS3Path"] == TRANSPORT_STARTUP
    _, rescanned = scan(client)
    assert rescanned.already_configured is True
    assert rescanned.plan.file_changes == []


def test_transport_281_with_the_users_own_unapplied_fix_plans_on_top_of_it_and_deploys_it():
    """The user removed the transport line themselves and uploaded it, without updating the environment."""
    client = load("transport-281")
    edited = "".join(line + "\n" for line in client.objects[TRANSPORT_STARTUP].splitlines() if "TRANSPORT" not in line)
    client.put_object_text("example-mwaa-bucket", TRANSPORT_STARTUP, edited)
    ctx, entry = scan(client)

    assert not issues(entry, FindingStatus.FAIL)
    assert issues(entry, FindingStatus.WARN)["unapplied_uploads"] == (
        f"{TRANSPORT_STARTUP} has a newer upload than the environment runs; the plan builds on it, "
        "and apply deploys it together with these changes"
    )
    assert {"OPENLINEAGE_URL", "OPENLINEAGE_API_KEY"} <= env_var_names(entry)

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, interpolate_api_key(compute_apply_actions(ctx, entry.plan), "0123456789abcdef"), [])

    assert "TRANSPORT" not in client.objects[TRANSPORT_STARTUP]
    assert "export OPENLINEAGE_URL=https://data-obs-intake.datad0g.com" in client.objects[TRANSPORT_STARTUP]
    assert client.environment["StartupScriptS3ObjectVersion"] == client.versions[TRANSPORT_STARTUP]
    _, rescanned = scan(client)
    assert rescanned.already_configured is True
    assert not rescanned.issues
