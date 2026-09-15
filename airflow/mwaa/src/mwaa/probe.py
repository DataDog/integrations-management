# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Orchestrates a full probe run against one MWAA environment."""

from airflow_shared.mwaa_client import MwaaClient, ObjectNotFoundError
from airflow_shared.reporter import Finding, Reporter

from .checks import ALL_CHECKS, ProbeContext, resolve_constraint_key
from .config import Config

WORKFLOW_TYPE = "mwaa-setup"


def build_context(client: MwaaClient, environment_name: str) -> ProbeContext:
    """Fetch everything the checks (and plan computation) need from AWS, once, up front."""
    environment = client.get_environment(environment_name)
    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]

    # RequirementsS3Path is optional in the MWAA API -- an environment that has
    # never had a requirements.txt configured simply won't have it set.
    requirements_path = environment.get("RequirementsS3Path")
    if requirements_path:
        requirements_text = client.get_object_text(
            bucket, requirements_path, environment.get("RequirementsS3ObjectVersion")
        )
    else:
        requirements_text = ""

    constraints_text = None
    constraints_key = resolve_constraint_key(requirements_text, environment.get("DagS3Path", "dags"))
    if constraints_key:
        try:
            constraints_text = client.get_object_text(bucket, constraints_key)
        except ObjectNotFoundError:
            constraints_text = None

    startup_script_text = None
    startup_script_path = environment.get("StartupScriptS3Path")
    if startup_script_path:
        try:
            startup_script_text = client.get_object_text(
                bucket, startup_script_path, environment.get("StartupScriptS3ObjectVersion")
            )
        except ObjectNotFoundError:
            startup_script_text = None

    return ProbeContext(
        environment=environment,
        requirements_text=requirements_text,
        constraints_text=constraints_text,
        startup_script_text=startup_script_text,
        client=client,
    )


def run_probe(config: Config, reporter: Reporter) -> list[Finding]:
    """Run every check against the configured environment, reporting as it goes."""
    client = MwaaClient(region=config.region)

    findings: list[Finding] = []
    with reporter.report_step("fetch_environment"):
        ctx = build_context(client, config.environment_name)

    with reporter.report_step("run_checks"):
        for check in ALL_CHECKS:
            finding = check(ctx)
            findings.append(finding)
            reporter.report_finding(finding)

    reporter.summary(findings)
    return findings
