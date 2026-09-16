# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Builds a ProbeContext: everything `scan` and `apply` need fetched from one MWAA environment.

Named for the checks.py machinery it feeds -- there used to be a standalone
`probe` command built around it (read-only diagnostics against one named
environment, no session involved), retired once `scan` started recording the
same checks as each environment's `issues` (see session.py).
"""

from airflow_shared.mwaa_client import MwaaClient, ObjectNotFoundError

from .checks import ProbeContext, resolve_constraint_key


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
