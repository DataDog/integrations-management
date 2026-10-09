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

from dataclasses import dataclass, field
from typing import Optional

from botocore.exceptions import ClientError

from airflow_shared.mwaa_client import MwaaClient
from airflow_shared.reporter import Finding, FindingStatus

from .base_constraints import BaseConstraints
from .plan import CONSTRAINTS_PATH, REQUIREMENTS_PATH, STARTUP_SCRIPT_PATH
from .pins import CONSTRAINT_LINE, DAGS_MOUNT_PREFIX, find_constraint_lines, find_wheel_references, resolve_constraint_s3_key
from .version_table import FLAGGED_VERSION_TABLE
from .startup_script import parse_exports

@dataclass
class ProbeContext:
    """Everything the checks need, fetched once by probe.py."""

    environment: dict
    requirements_text: str
    # current content of the constraints file at constraints_path (None if it doesn't exist)
    constraints_text: Optional[str]
    startup_script_text: Optional[str]
    client: MwaaClient
    # only resolved for flagged versions -- the only ones whose plan writes a constraints file
    base_constraints: Optional[BaseConstraints] = None
    # filenames of wheels requirements.txt references whose S3 objects exist -- only
    # resolved for versions that install from wheels (2.7.2)
    present_wheel_files: frozenset[str] = frozenset()
    # the `dags/...` label of the constraints file a flagged plan writes: the file
    # requirements.txt references under the DAGs mount, else dags/constraints.txt,
    # or dags/constraints-datadog.txt when an unreferenced dags/constraints.txt exists
    constraints_path: str = CONSTRAINTS_PATH
    # labels of the requirements.txt/startup.sh a plan writes: the -datadog sibling (plan.py)
    # when the environment has no S3 path configured for one but its default key is taken
    requirements_path: str = REQUIREMENTS_PATH
    startup_script_path: str = STARTUP_SCRIPT_PATH
    # label -> latest S3 VersionId (None = doesn't exist) of every file the plan reads
    # or might write; labels whose version couldn't be read are in file_version_errors
    file_versions: dict[str, Optional[str]] = field(default_factory=dict)
    file_version_errors: dict[str, str] = field(default_factory=dict)


def resolve_constraint_key(requirements_text: str, dag_s3_path: str) -> Optional[str]:
    """Find the --constraint line in requirements.txt and resolve it to an S3 key.

    Shared by check_constraint_path and probe.py, which needs the same
    resolution to fetch constraints.txt for plan computation.
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


def check_base_constraints(ctx: ProbeContext) -> Finding:
    """A flagged version needs a safe, full base constraints file to plan its package changes.

    See base_constraints.py for every way that can fail (an unreachable
    download, an upstream URL for the wrong Airflow/Python version, ...);
    base.error says which, and what to do about it. Without one, the only
    file this tool could write is a pins-only constraints file, which
    unconstrains everything else, so the plan leaves the package changes out
    instead and this records why.
    """
    base = ctx.base_constraints
    if base is None or base.text is not None:
        return Finding("base_constraints", FindingStatus.PASS, "base constraints file read" if base else "no base constraints file needed")
    return Finding(
        "base_constraints",
        FindingStatus.FAIL,
        base.error,
        "The plan leaves out every OpenLineage package change until this is fixed: a constraints file holding "
        "only the OpenLineage pins would unconstrain every other package.",
    )


def check_constraint_directives(ctx: ProbeContext) -> Finding:
    """A flagged version's requirements.txt can have at most one --constraint line for the plan to fix it.

    pip enforces every --constraint line it's given, so with two, repointing
    one at the patched constraints.txt would leave the other's old
    OpenLineage pins still in force. The plan leaves the package changes out
    in that case, and this records why.
    """
    lines = find_constraint_lines(ctx.requirements_text)
    if len(lines) <= 1 or ctx.environment.get("AirflowVersion", "") not in FLAGGED_VERSION_TABLE:
        return Finding("constraint_directives", FindingStatus.PASS, "requirements.txt has at most one --constraint line that matters")
    return Finding(
        "constraint_directives",
        FindingStatus.FAIL,
        f"requirements.txt has {len(lines)} --constraint lines, so the plan leaves out every OpenLineage package change",
        "\n".join(lines) + "\npip enforces all of them. Consolidate them into one and re-run scan.",
    )


def unapplied_uploads(ctx: ProbeContext) -> list[str]:
    """Labels of requirements.txt/startup.sh whose latest S3 version isn't the one the environment is configured with.

    Someone uploaded a newer file without updating the environment. A plan
    computed from the configured version would silently discard their
    upload; one computed from the newer one would silently apply it. Only
    a file the environment is actually configured with, at a pinned
    version, counts -- an unconfigured one at the default key is an orphan
    the plan leaves alone (see probe.py), and an unpinned one means MWAA
    uses the latest.
    """
    configured = (
        (REQUIREMENTS_PATH, "RequirementsS3Path", "RequirementsS3ObjectVersion"),
        (STARTUP_SCRIPT_PATH, "StartupScriptS3Path", "StartupScriptS3ObjectVersion"),
    )
    return [
        label
        for label, path_key, version_key in configured
        if ctx.environment.get(path_key)
        and ctx.environment.get(version_key)
        and label in ctx.file_versions
        and ctx.file_versions[label] != ctx.environment[version_key]
    ]


def check_unapplied_uploads(ctx: ProbeContext) -> Finding:
    """requirements.txt/startup.sh must not have a newer upload the environment isn't configured with yet.

    The plan leaves out that file's changes (session.py) -- all package
    changes for requirements.txt, the env-var changes for startup.sh.
    """
    labels = unapplied_uploads(ctx)
    if not labels:
        return Finding("unapplied_uploads", FindingStatus.PASS, "the environment is configured with the latest requirements.txt and startup.sh")
    return Finding(
        "unapplied_uploads",
        FindingStatus.FAIL,
        f"{' and '.join(labels)} {'has a newer upload' if len(labels) == 1 else 'have newer uploads'} than the environment "
        f"is configured with; apply or discard {'it' if len(labels) == 1 else 'them'}, then re-scan",
        "Until then the plan leaves out the changes to "
        + (" and ".join(labels))
        + ".",
    )


def check_file_versions(ctx: ProbeContext) -> Finding:
    """Every file the plan reads or writes needs a readable latest VersionId, for apply's staleness check.

    The plan leaves out the changes that depend on a file whose version
    couldn't be read (session.py).
    """
    if not ctx.file_version_errors:
        return Finding("file_versions", FindingStatus.PASS, "read the latest version of every file the plan depends on")
    return Finding(
        "file_versions",
        FindingStatus.FAIL,
        f"couldn't read the latest S3 version of {', '.join(ctx.file_version_errors)}, so the plan leaves out the changes that depend on it",
        "\n".join(f"{label}: {error}" for label, error in ctx.file_version_errors.items())
        + "\nRe-run scan once these can be read (HeadObject, with s3:ListBucket on the bucket).",
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

    from_startup = parse_exports(ctx.startup_script_text or "")

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


