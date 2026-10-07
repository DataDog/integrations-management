# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Builds a ProbeContext: everything `scan` and `apply` need fetched from one MWAA environment.

Named for the checks.py machinery it feeds -- there used to be a standalone
`probe` command built around it (read-only diagnostics against one named
environment, no session involved), retired once `scan` started recording the
same checks as each environment's `issues` (see session.py).
"""

from botocore.exceptions import ClientError

from airflow_shared.mwaa_client import MwaaClient, ObjectNotFoundError

from .base_constraints import resolve_base_constraints
from .checks import ProbeContext, resolve_constraint_key
from .fetch import fetch_bytes
from .pins import find_wheel_references, resolve_constraint_s3_key
from .version_table import FLAGGED_VERSION_TABLE


def build_context(client: MwaaClient, environment_name: str) -> ProbeContext:
    """Fetch everything the checks (and plan computation) need, once, up front.

    Everything comes from AWS except a flagged version's base constraints
    file when it isn't already a local S3 object (see base_constraints.py) --
    that's a plain HTTPS GET.
    """
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

    base_constraints = None
    present_wheel_files: set[str] = set()
    flagged_entry = FLAGGED_VERSION_TABLE.get(environment.get("AirflowVersion", ""))
    if flagged_entry:
        base_constraints = resolve_base_constraints(
            flagged_entry.airflow_version, requirements_text, constraints_text, f"s3://{bucket}/{constraints_key}", fetch_bytes
        )
    if flagged_entry and flagged_entry.wheel_only_packages:
        for ref in find_wheel_references(requirements_text):
            key = resolve_constraint_s3_key(ref, environment.get("DagS3Path", "dags"))
            try:
                if key and client.object_exists(bucket, key):
                    present_wheel_files.add(ref.rsplit("/", 1)[-1])
            except ClientError:
                # e.g. a 403 for a missing key without s3:ListBucket -- treat it as
                # missing, so the plan re-uploads it rather than trust it's there
                pass

    return ProbeContext(
        environment=environment,
        requirements_text=requirements_text,
        constraints_text=constraints_text,
        startup_script_text=startup_script_text,
        client=client,
        base_constraints=base_constraints,
        present_wheel_files=frozenset(present_wheel_files),
    )
