# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Builds a ProbeContext: everything `scan` and `apply` need fetched from one MWAA environment.

Named for the checks.py machinery it feeds -- there used to be a standalone
`probe` command built around it (read-only diagnostics against one named
environment, no session involved), retired once `scan` started recording the
same checks as each environment's `issues` (see session.py).
"""

from typing import Optional

from botocore.exceptions import ClientError

from airflow_shared.mwaa_client import MwaaClient, ObjectNotFoundError, VersionIdUnavailable

from .apply import real_key_for_path
from .base_constraints import BaseConstraints, resolve_base_constraints
from .checks import ProbeContext, resolve_constraint_key
from .fetch import fetch_bytes
from .pins import DAGS_MOUNT_PREFIX, find_wheel_references
from .plan import CONSTRAINTS_PATH, DATADOG_CONSTRAINTS_PATH, REQUIREMENTS_PATH, STARTUP_SCRIPT_PATH
from .version_table import FLAGGED_VERSION_TABLE, datadog_wheel_filename


def build_context(client: MwaaClient, environment_name: str) -> ProbeContext:
    """Fetch everything the checks (and plan computation) need, once, up front.

    Everything comes from AWS except a flagged version's base constraints
    file when it isn't already a local S3 object (see base_constraints.py) --
    that's a plain HTTPS GET.

    Also records file_versions: the latest S3 VersionId (None if it doesn't
    exist) of every file the plan reads or might write, keyed by the plan's
    path labels. Apply refuses to run if any of them changed since (see
    apply.check_files_unchanged), which is what lets it trust the plan
    instead of re-deriving it from whatever's there by then. Each file gets
    exactly one HeadObject, and every decision and content read about it
    uses that result -- an object appearing between two looks can't make
    the plan and its fingerprint disagree.
    """
    environment = client.get_environment(environment_name)
    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    dag_s3_path = environment.get("DagS3Path", "dags").rstrip("/")
    flagged_entry = FLAGGED_VERSION_TABLE.get(environment.get("AirflowVersion", ""))
    file_versions: dict[str, Optional[str]] = {}
    file_version_errors: dict[str, str] = {}

    def fingerprint(label: str) -> tuple[bool, Optional[str]]:
        """(readable, latest VersionId) for one label, recorded in file_versions/file_version_errors."""
        try:
            file_versions[label] = client.latest_version_id(bucket, real_key_for_path(environment, label))
        except (ClientError, VersionIdUnavailable) as exc:
            file_version_errors[label] = str(exc)
            return False, None
        return True, file_versions[label]

    # the plan is computed from the configured versions; check_unapplied_uploads
    # compares them with the latest ones fingerprinted here
    # a configured path with no pinned version means MWAA uses the latest, so read
    # exactly the latest version fingerprinted, not whatever's latest a moment later
    _, requirements_version = fingerprint(REQUIREMENTS_PATH)
    requirements_path = environment.get("RequirementsS3Path")
    if requirements_path:
        requirements_text = client.get_object_text(
            bucket, requirements_path, environment.get("RequirementsS3ObjectVersion") or requirements_version
        )
    else:
        # optional in the MWAA API -- never configured
        requirements_text = ""

    _, startup_script_version = fingerprint(STARTUP_SCRIPT_PATH)
    startup_script_text = None
    startup_script_path = environment.get("StartupScriptS3Path")
    if startup_script_path:
        try:
            startup_script_text = client.get_object_text(
                bucket, startup_script_path, environment.get("StartupScriptS3ObjectVersion") or startup_script_version
            )
        except ObjectNotFoundError:
            startup_script_text = None

    base_constraints = None
    constraints_path = CONSTRAINTS_PATH
    constraints_text = None
    constraints_key = resolve_constraint_key(requirements_text, dag_s3_path)
    if flagged_entry and constraints_key:
        constraints_path = f"dags/{constraints_key.removeprefix(dag_s3_path + '/')}"
        _, version = fingerprint(constraints_path)
        if version:
            constraints_text = client.get_object_text(bucket, constraints_key, version)
        base_constraints = resolve_base_constraints(
            flagged_entry.airflow_version, requirements_text, constraints_text, f"s3://{bucket}/{constraints_key}", fetch_bytes
        )
    elif flagged_entry:
        # nothing local is referenced, so a dags/constraints.txt that exists isn't this
        # environment's to patch or overwrite -- it may be another environment's
        readable, orphan_version = fingerprint(CONSTRAINTS_PATH)
        if not readable:
            reason = file_version_errors.pop(CONSTRAINTS_PATH)  # reported as the base_constraints issue instead
            base_constraints = BaseConstraints(
                source=None,
                text=None,
                error=f"couldn't tell whether {CONSTRAINTS_PATH} exists ({reason}); re-run scan with s3:ListBucket on the bucket",
            )
        else:
            if orphan_version:
                constraints_path = DATADOG_CONSTRAINTS_PATH
                _, version = fingerprint(constraints_path)
                if version:
                    constraints_text = client.get_object_text(bucket, real_key_for_path(environment, constraints_path), version)
            base_constraints = resolve_base_constraints(flagged_entry.airflow_version, requirements_text, None, "", fetch_bytes)

    present_wheel_files: set[str] = set()
    if flagged_entry and flagged_entry.wheel_only_packages:
        for package in flagged_entry.wheel_only_packages:
            fingerprint(f"dags/{datadog_wheel_filename(package, flagged_entry.target_versions[package])}")
        for ref in find_wheel_references(requirements_text):
            if ref.startswith(DAGS_MOUNT_PREFIX):
                _, version = fingerprint(f"dags/{ref.removeprefix(DAGS_MOUNT_PREFIX)}")
                if version:
                    present_wheel_files.add(ref.rsplit("/", 1)[-1])

    return ProbeContext(
        environment=environment,
        requirements_text=requirements_text,
        constraints_text=constraints_text,
        startup_script_text=startup_script_text,
        client=client,
        base_constraints=base_constraints,
        present_wheel_files=frozenset(present_wheel_files),
        constraints_path=constraints_path,
        file_versions=file_versions,
        file_version_errors=file_version_errors,
    )
