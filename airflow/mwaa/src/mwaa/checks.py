# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Probe checks for a live MWAA environment's OpenLineage onboarding setup.

Each check is a pure function: (ProbeContext) -> Finding. None of them mutate
AWS state; the ones that need more data than GetEnvironment already returned
call back into the MwaaClient held on the context (S3 reads, IAM policy
simulation).

The subset that matters for whether it's safe to apply a plan (see
_ISSUE_CHECKS in session.py) is what `scan` records as each environment's
`issues`; there is no longer a standalone command that runs all of these.

Grounded in two sources:
  * Datadog's public MWAA/OpenLineage upgrade guide
    (docs.datadoghq.com/data_observability/jobs_monitoring/airflow_mwaa_upgrade.md),
    which documents the requirements.txt/constraints.txt upgrade procedure for
    Airflow 2.7.2/2.8.1/2.9.2 and calls out several of these checks directly as
    troubleshooting steps.
  * do-test-env's terraform/mwaa_setup_probe.tf, which raised the one question
    the public doc does not answer: when OpenLineage is configured via both the
    MWAA startup script and airflow_configuration_options, which one wins.
"""

import re
from dataclasses import dataclass
from typing import Optional

from botocore.exceptions import ClientError

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Finding, FindingStatus

from .pins import (
    COMMON_COMPAT_PACKAGE,
    CONSTRAINT_LINE,
    DAGS_MOUNT_PREFIX,
    OPENLINEAGE_PACKAGES,
    find_wheel_references,
    parse_pins,
    resolve_constraint_s3_key,
)

# Airflow versions whose MWAA-default constraints pin an OpenLineage provider
# with known issues, per Datadog's onboarding docs.
FLAGGED_AIRFLOW_VERSIONS = {"2.7.2", "2.8.1", "2.9.2"}

_EXPORT_LINE = re.compile(
    r"^\s*export\s+(AIRFLOW__OPENLINEAGE__\w+|OPENLINEAGE_\w+)=(.*)$",
    re.MULTILINE,
)


def _strip_matching_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


@dataclass
class ProbeContext:
    """Everything the checks need, fetched once by probe.py."""

    environment: dict
    requirements_text: str
    constraints_text: Optional[str]
    startup_script_text: Optional[str]
    client: MwaaClient


def resolve_constraint_key(requirements_text: str, dag_s3_path: str) -> Optional[str]:
    """Find the --constraint line in requirements.txt and resolve it to an S3 key.

    Shared by check_constraint_path and probe.py, which needs the same
    resolution to fetch constraints.txt for check_requirements_constraints_match.
    Returns None if there's no --constraint line, or it isn't under the DAGs mount.
    """
    match = CONSTRAINT_LINE.search(requirements_text)
    if not match:
        return None
    return resolve_constraint_s3_key(match.group(1), dag_s3_path)


def check_constraint_path(ctx: ProbeContext) -> Finding:
    """The --constraint line in requirements.txt must resolve to a real S3 object."""
    match = CONSTRAINT_LINE.search(ctx.requirements_text)
    if not match:
        return Finding(
            "constraint_path",
            FindingStatus.WARN,
            "requirements.txt has no --constraint line",
            "MWAA will fall back to its own default constraints for this Airflow version, "
            "which is exactly what pins a broken OpenLineage provider on 2.7.2/2.8.1/2.9.2.",
        )

    constraint_path = match.group(1)
    dag_s3_path = ctx.environment.get("DagS3Path", "dags")
    resolved_key = resolve_constraint_s3_key(constraint_path, dag_s3_path)
    if resolved_key is None:
        return Finding(
            "constraint_path",
            FindingStatus.WARN,
            f"--constraint path is not under {DAGS_MOUNT_PREFIX}, cannot verify it resolves to an S3 object",
            f"path: {constraint_path}",
        )

    bucket = ctx.environment["SourceBucketArn"].rsplit(":", 1)[-1]
    if ctx.client.object_exists(bucket, resolved_key):
        return Finding("constraint_path", FindingStatus.PASS, f"constraints file found at s3://{bucket}/{resolved_key}")
    return Finding(
        "constraint_path",
        FindingStatus.FAIL,
        "requirements.txt references a constraints file that does not exist",
        f"expected s3://{bucket}/{resolved_key} (from --constraint {constraint_path})",
    )


def check_wheel_references(ctx: ProbeContext) -> Finding:
    """Every .whl file requirements.txt references must exist as an S3 object.

    Airflow 2.7.2's documented upgrade path has customers upload
    Datadog-patched wheels by hand. A missing or renamed wheel becomes a
    "could not find a version that satisfies" pip failure 20-30 minutes into
    an environment update; resolving the reference against S3 up front turns
    that into an instant pre-flight finding instead.
    """
    wheel_refs = find_wheel_references(ctx.requirements_text)
    if not wheel_refs:
        return Finding("wheel_references", FindingStatus.PASS, "requirements.txt references no .whl files")

    dag_s3_path = ctx.environment.get("DagS3Path", "dags")
    bucket = ctx.environment["SourceBucketArn"].rsplit(":", 1)[-1]

    missing = []
    unresolvable = []
    for ref in wheel_refs:
        key = resolve_constraint_s3_key(ref, dag_s3_path)
        if key is None:
            unresolvable.append(ref)
            continue
        if not ctx.client.object_exists(bucket, key):
            missing.append(f"{ref} -> s3://{bucket}/{key}")

    if missing:
        return Finding(
            "wheel_references",
            FindingStatus.FAIL,
            "requirements.txt references .whl file(s) that do not exist in S3",
            "\n".join(missing),
        )
    if unresolvable:
        return Finding(
            "wheel_references",
            FindingStatus.WARN,
            f"{len(unresolvable)} referenced wheel(s) are outside {DAGS_MOUNT_PREFIX}, cannot verify they exist",
            "\n".join(unresolvable),
        )
    return Finding("wheel_references", FindingStatus.PASS, f"all {len(wheel_refs)} referenced wheel(s) exist in S3")


def check_openlineage_pins(ctx: ProbeContext) -> Finding:
    """OpenLineage-family packages should be explicitly pinned on flagged Airflow versions."""
    airflow_version = ctx.environment.get("AirflowVersion", "")
    pins = parse_pins(ctx.requirements_text)
    pinned_ol_packages = [pkg for pkg in OPENLINEAGE_PACKAGES if pkg in pins]

    if not pinned_ol_packages:
        if airflow_version in FLAGGED_AIRFLOW_VERSIONS:
            return Finding(
                "openlineage_pins",
                FindingStatus.FAIL,
                f"no OpenLineage packages are pinned in requirements.txt on Airflow {airflow_version}",
                "This version's MWAA-default constraints pin a known-broken OpenLineage provider. "
                "See Datadog's MWAA upgrade guide for the packages and versions to pin.",
            )
        return Finding(
            "openlineage_pins",
            FindingStatus.PASS,
            f"no explicit OpenLineage pins on Airflow {airflow_version} (not one of the flagged versions)",
        )

    if "apache-airflow-providers-openlineage" in pinned_ol_packages and COMMON_COMPAT_PACKAGE not in pins:
        return Finding(
            "openlineage_pins",
            FindingStatus.WARN,
            f"{COMMON_COMPAT_PACKAGE} is not pinned alongside the OpenLineage provider",
            "This package is easy to forget and is required by the documented upgrade path.",
        )

    return Finding(
        "openlineage_pins",
        FindingStatus.PASS,
        f"OpenLineage packages are explicitly pinned: {', '.join(sorted(pinned_ol_packages))}",
    )


def check_requirements_constraints_match(ctx: ProbeContext) -> Finding:
    """Shared package pins must agree between requirements.txt and constraints.txt."""
    if ctx.constraints_text is None:
        return Finding(
            "requirements_constraints_match",
            FindingStatus.WARN,
            "constraints.txt could not be fetched, skipping version cross-check",
        )

    req_pins = parse_pins(ctx.requirements_text)
    con_pins = parse_pins(ctx.constraints_text)

    mismatches = [
        f"{pkg}: requirements.txt has {req_pins[pkg]}, constraints.txt has {con_pins[pkg]}"
        for pkg in OPENLINEAGE_PACKAGES + (COMMON_COMPAT_PACKAGE,)
        if pkg in req_pins and pkg in con_pins and req_pins[pkg] != con_pins[pkg]
    ]

    if mismatches:
        return Finding(
            "requirements_constraints_match",
            FindingStatus.FAIL,
            "requirements.txt and constraints.txt disagree on pinned versions",
            "\n".join(mismatches),
        )
    return Finding(
        "requirements_constraints_match",
        FindingStatus.PASS,
        "requirements.txt and constraints.txt agree on every shared pin",
    )


def _config_key_to_env_var(config_key: str) -> Optional[str]:
    if not config_key.startswith("openlineage."):
        return None
    return "AIRFLOW__OPENLINEAGE__" + config_key.split(".", 1)[1].upper()


def check_openlineage_precedence(ctx: ProbeContext) -> Finding:
    """Flag when OpenLineage is configured via both the startup script and config options.

    do-test-env's mwaa_setup_probe.tf exists because nothing documents which
    mechanism wins when both set the same variable. This check can only detect
    the ambiguity from the two source configs -- confirming which one actually
    won requires reading a worker's resolved environment, e.g. from the
    `openlineage_config_probe` DAG's task log if that DAG is present.
    """
    config_options = ctx.environment.get("AirflowConfigurationOptions", {})
    from_config: dict[str, str] = {}
    for key, value in config_options.items():
        env_var = _config_key_to_env_var(key)
        if env_var:
            from_config[env_var] = str(value)

    from_startup: dict[str, str] = {}
    if ctx.startup_script_text:
        for name, value in _EXPORT_LINE.findall(ctx.startup_script_text):
            from_startup[name] = _strip_matching_quotes(value)

    conflicts = [
        f"{name}: startup script sets {from_startup[name]!r}, airflow_configuration_options sets {from_config[name]!r}"
        for name in sorted(set(from_config) & set(from_startup))
        if from_config[name] != from_startup[name]
    ]

    if conflicts:
        return Finding(
            "openlineage_precedence",
            FindingStatus.WARN,
            "OpenLineage is configured via both the startup script and airflow_configuration_options, with different values",
            "\n".join(conflicts)
            + "\nCheck a worker's resolved environment (e.g. a task log) to see which one is actually live.",
        )
    return Finding(
        "openlineage_precedence",
        FindingStatus.PASS,
        "no conflicting OpenLineage configuration between the startup script and airflow_configuration_options",
    )


def check_execution_role_s3_access(ctx: ProbeContext) -> Finding:
    """The execution role must be able to read the source bucket, not just the caller's own credentials.

    MWAA is presumably running today with whatever access the execution role
    already has -- the risk this catches is narrower: a plan that writes to a
    *new* S3 key (e.g. a constraints.txt that didn't exist before) can land
    outside a role policy scoped to a specific prefix, which only breaks once
    the environment is asked to read that new key on its next update.

    Simulating the role's own policy needs iam:SimulatePrincipalPolicy on the
    *caller's* credentials, which a customer running this CLI may not have.
    That's a permissions gap in this check, not in the execution role, so it
    degrades to "not verified" rather than failing the whole check.
    """
    role_arn = ctx.environment["ExecutionRoleArn"]
    bucket_arn = ctx.environment["SourceBucketArn"]
    try:
        access = ctx.client.simulate_s3_read_access(role_arn, bucket_arn)
    except ClientError as exc:
        return Finding(
            "execution_role_s3_access",
            FindingStatus.WARN,
            "could not verify the execution role's S3 access",
            f"{exc}\nThis means the check couldn't run, not that the execution role lacks access. "
            "It usually means the caller's own credentials lack iam:SimulatePrincipalPolicy.",
        )
    denied = [action for action, allowed in access.items() if not allowed]
    if denied:
        return Finding(
            "execution_role_s3_access",
            FindingStatus.FAIL,
            "execution role is missing S3 permissions it needs",
            f"denied: {', '.join(denied)} on {bucket_arn}",
        )
    return Finding("execution_role_s3_access", FindingStatus.PASS, "execution role can read the source bucket")


