# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Probe checks for a live MWAA environment's OpenLineage onboarding setup.

Each check is a pure function: (ProbeContext) -> Finding. None of them mutate
AWS state; the ones that need more data than GetEnvironment already returned
call back into the MwaaClient held on the context (S3 reads, IAM policy
simulation, CloudWatch log reads, route table reads).

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

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Finding, FindingStatus

# MWAA mounts the DAGs folder at this path inside the container regardless of
# the S3 prefix (dag_s3_path) the environment is configured with.
DAGS_MOUNT_PREFIX = "/usr/local/airflow/dags/"

# Airflow versions whose MWAA-default constraints pin an OpenLineage provider
# with known issues, per Datadog's onboarding docs.
FLAGGED_AIRFLOW_VERSIONS = {"2.7.2", "2.8.1", "2.9.2"}

OPENLINEAGE_PACKAGES = (
    "apache-airflow-providers-openlineage",
    "openlineage-python",
    "openlineage-integration-common",
    "openlineage-sql",
    "apache-airflow-providers-common-sql",
)
COMMON_COMPAT_PACKAGE = "apache-airflow-providers-common-compat"

_CONSTRAINT_LINE = re.compile(r'^\s*--constraint\s+"?([^"\s]+)"?', re.MULTILINE)
_PIN_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-]+)", re.MULTILINE)
_EXPORT_LINE = re.compile(
    r"^\s*export\s+(AIRFLOW__OPENLINEAGE__\w+|OPENLINEAGE_\w+)=(.*)$",
    re.MULTILINE,
)


def _strip_matching_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value
_DEPENDENCY_ERROR_PATTERNS = ("ResolutionImpossible", "ERROR: Cannot install", "ERROR: No matching distribution")


@dataclass
class ProbeContext:
    """Everything the checks need, fetched once by probe.py."""

    environment: dict
    requirements_text: str
    constraints_text: Optional[str]
    startup_script_text: Optional[str]
    client: MwaaClient


def _parse_pins(text: str) -> dict[str, str]:
    return {name.lower(): version for name, version in _PIN_LINE.findall(text)}


def _resolve_constraint_s3_key(constraint_path: str, dag_s3_path: str) -> Optional[str]:
    """Resolve a `--constraint /usr/local/airflow/dags/...` path to an S3 key.

    Returns None if the path isn't under the DAGs mount, which this check
    can't resolve back to an S3 object.
    """
    if not constraint_path.startswith(DAGS_MOUNT_PREFIX):
        return None
    relative = constraint_path[len(DAGS_MOUNT_PREFIX) :]
    return f"{dag_s3_path.rstrip('/')}/{relative}"


def resolve_constraint_key(requirements_text: str, dag_s3_path: str) -> Optional[str]:
    """Find the --constraint line in requirements.txt and resolve it to an S3 key.

    Shared by check_constraint_path and probe.py, which needs the same
    resolution to fetch constraints.txt for check_requirements_constraints_match.
    Returns None if there's no --constraint line, or it isn't under the DAGs mount.
    """
    match = _CONSTRAINT_LINE.search(requirements_text)
    if not match:
        return None
    return _resolve_constraint_s3_key(match.group(1), dag_s3_path)


def check_constraint_path(ctx: ProbeContext) -> Finding:
    """The --constraint line in requirements.txt must resolve to a real S3 object."""
    match = _CONSTRAINT_LINE.search(ctx.requirements_text)
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
    resolved_key = _resolve_constraint_s3_key(constraint_path, dag_s3_path)
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


def check_openlineage_pins(ctx: ProbeContext) -> Finding:
    """OpenLineage-family packages should be explicitly pinned on flagged Airflow versions."""
    airflow_version = ctx.environment.get("AirflowVersion", "")
    pins = _parse_pins(ctx.requirements_text)
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

    req_pins = _parse_pins(ctx.requirements_text)
    con_pins = _parse_pins(ctx.constraints_text)

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
    """The execution role must be able to read the source bucket, not just the caller's own credentials."""
    role_arn = ctx.environment["ExecutionRoleArn"]
    bucket_arn = ctx.environment["SourceBucketArn"]
    access = ctx.client.simulate_s3_read_access(role_arn, bucket_arn)
    denied = [action for action, allowed in access.items() if not allowed]
    if denied:
        return Finding(
            "execution_role_s3_access",
            FindingStatus.FAIL,
            "execution role is missing S3 permissions it needs",
            f"denied: {', '.join(denied)} on {bucket_arn}",
        )
    return Finding("execution_role_s3_access", FindingStatus.PASS, "execution role can read the source bucket")


def check_install_log_errors(ctx: ProbeContext) -> Finding:
    """Scan the DAGProcessing log group for pip dependency-resolution failures."""
    name = ctx.environment["Name"]
    log_group = f"airflow-{name}-DAGProcessing"
    matches = []
    for pattern in _DEPENDENCY_ERROR_PATTERNS:
        matches.extend(ctx.client.filter_log_events(log_group, f'"{pattern}"', limit=5))

    if matches:
        return Finding(
            "install_log_errors",
            FindingStatus.FAIL,
            "found dependency-resolution errors in the DAGProcessing log",
            "\n".join(matches[:5]),
        )
    return Finding(
        "install_log_errors",
        FindingStatus.PASS,
        "no dependency-resolution errors found in the DAGProcessing log",
    )


def check_network_egress(ctx: ProbeContext) -> Finding:
    """Every MWAA subnet needs a route to the internet (NAT or IGW) for pip to install anything."""
    subnet_ids = ctx.environment.get("NetworkConfiguration", {}).get("SubnetIds", [])
    if not subnet_ids:
        return Finding("network_egress", FindingStatus.WARN, "environment has no subnets in its NetworkConfiguration")

    egress = ctx.client.describe_subnet_egress(subnet_ids)
    no_egress = [e.subnet_id for e in egress if not (e.has_nat_route or e.has_internet_gateway_route)]
    if no_egress:
        return Finding(
            "network_egress",
            FindingStatus.FAIL,
            "some subnets have no route to the internet",
            f"subnets without a NAT/internet gateway route: {', '.join(no_egress)}",
        )
    return Finding("network_egress", FindingStatus.PASS, "all subnets have a route to the internet")


ALL_CHECKS = (
    check_constraint_path,
    check_openlineage_pins,
    check_requirements_constraints_match,
    check_openlineage_precedence,
    check_execution_role_s3_access,
    check_install_log_errors,
    check_network_egress,
)
