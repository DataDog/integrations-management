# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Five real MWAA environments the scan used to get wrong -- see real_environments/README.md."""

import json
from pathlib import Path

from airflow_shared.reporter import FindingStatus
from mwaa.apply import apply_to_environment, check_files_unchanged, compute_apply_actions
from mwaa.plan import ConstraintDirectiveChange, EnvVarChange, PinChange
from mwaa.probe import build_context
from mwaa.session import build_session

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
    assert "openlineage_provider" in warnings
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
    # still has upstream's openlineage_sql==1.7.0 next to the patched pin, which has to go
    package_changes = [fc for fc in entry.plan.file_changes if not isinstance(fc, EnvVarChange)]
    assert package_changes == [PinChange(path="dags/constraints.txt", package="openlineage-sql", from_version="1.7.0", to_version="1.24.2")]


def test_sandbox_281_writes_datadog_copies_next_to_its_orphaned_files():
    client = load("sandbox-281")
    ctx, entry = scan(client)

    assert entry.already_configured is False
    assert not issues(entry, FindingStatus.FAIL)
    assert "constraint_path" not in issues(entry, FindingStatus.WARN)  # the plan adds the --constraint line itself
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, EnvVarChange)} == {"dags/startup-datadog.sh"}
    assert env_var_names(entry) == {
        "OPENLINEAGE_URL",
        "OPENLINEAGE_API_KEY",
        "AIRFLOW__OPENLINEAGE__NAMESPACE",
        "AIRFLOW__OPENLINEAGE__CONFIG_PATH",
        "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS",
    }
    assert {fc.path for fc in entry.plan.file_changes if isinstance(fc, PinChange)} == {"dags/constraints-datadog.txt", "requirements.txt"}
    assert any(isinstance(fc, ConstraintDirectiveChange) for fc in entry.plan.file_changes)
    assert "dags/startup.sh already exists" in entry.plan.rationale
    assert "startup-datadog.sh" in entry.plan.rationale

    check_files_unchanged(client, ctx.environment, entry.plan, entry.file_versions)
    apply_to_environment(client, ctx, compute_apply_actions(ctx, entry.plan), [])

    assert client.objects["probe/sandbox/dags/startup.sh"] == (FIXTURES / "sandbox-281" / "someone-elses-startup.sh").read_text()
    assert "OPENLINEAGE_URL=https://data-obs-intake.datad0g.com" in client.objects["probe/sandbox/dags/startup-datadog.sh"]
    assert client.update_environment.call_args.kwargs["StartupScriptS3Path"] == "probe/sandbox/dags/startup-datadog.sh"


def test_blank_321_writes_requirements_datadog_txt_beside_an_existing_unconfigured_requirements_txt():
    client = load("blank-321")
    ctx, entry = scan(client)

    assert entry.already_configured is False
    assert not issues(entry, FindingStatus.FAIL)
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
