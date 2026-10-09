# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Turns a Plan into real file uploads and an MWAA environment update.

A session never carries file content, so the files are re-fetched here (via
ProbeContext, built fresh by probe) to patch against. check_files_unchanged
first proves each one is still the exact S3 version the plan was computed
from -- anything changed means re-scan, never patch -- so the plan itself is
applied as-is. Nothing here is ever printed or persisted outside this process.

REQUIREMENTS_PATH/STARTUP_SCRIPT_PATH and the `dags/...` constraints and
wheel labels (plan.py) are display labels -- never literal S3 keys.
Reading (current_text_for_path) always went through ctx's already-correctly-
fetched content, so it never cared. Writing didn't used to make that
distinction, and it bit a real environment for real: an environment whose
actual RequirementsS3Path lived under a `setup-probe/<name>/` prefix got its
upload sent to the literal key "requirements.txt" instead -- which happened
to be a completely different environment's real file, sharing the same
bucket. real_key_for_path exists so every write goes through the SAME
environment-specific key resolution reads already use.
"""

from dataclasses import dataclass
from typing import Any, Optional

from airflow_shared.mwaa_client import MwaaClient, VersionIdUnavailable

from botocore.exceptions import ClientError

from .checks import ProbeContext
from .fetch import fetch_bytes
from .patch import patch_env_vars, patch_pins, patch_wheel_references, set_constraint_line
from .pins import DAGS_MOUNT_PREFIX
from .plan import (
    DATADOG_REQUIREMENTS_PATH,
    REQUIREMENTS_PATH,
    REQUIREMENTS_PATHS,
    STARTUP_SCRIPT_PATH,
    STARTUP_SCRIPT_PATHS,
    ConstraintDirectiveChange,
    EnvVarChange,
    PinChange,
    Plan,
    WheelReference,
)
from .startup_script import interpolate_api_key as _substitute_api_key


@dataclass(frozen=True)
class FileUpload:
    """One file's final content, ready to write to S3, alongside what it's replacing.

    `path` stays a generic plan.py label (REQUIREMENTS_PATH etc.) for display
    purposes -- render_unified_diff doesn't need a real key. apply_to_environment
    resolves the real key itself, right before writing.
    """

    path: str
    old_content: str
    content: str
    action: str  # "create" | "update"


def _is_constraints_path(path: str) -> bool:
    """Every `dags/...` label a plan uses other than startup.sh names its constraints file."""
    return path not in STARTUP_SCRIPT_PATHS and path.startswith("dags/")


def current_text_for_path(ctx: ProbeContext, path: str) -> str:
    """The real current content for one of the three files a plan ever touches."""
    if _is_constraints_path(path):
        return ctx.constraints_text or ""
    if path in REQUIREMENTS_PATHS:
        return ctx.requirements_text
    if path in STARTUP_SCRIPT_PATHS:
        return ctx.startup_script_text or ""
    raise ValueError(f"don't know how to apply a change to {path!r}")


def _default_requirements_key(dag_s3_path: str) -> str:
    """Best-effort key for an environment that has never had requirements.txt
    configured (RequirementsS3Path absent from GetEnvironment): every environment
    this tool has seen keeps requirements.txt as a sibling of its DAGs prefix, one
    level up (e.g. dags="setup-probe/x/dags" -> requirements="setup-probe/x/requirements.txt";
    dags="dags" -> requirements="requirements.txt")."""
    parent = dag_s3_path.rsplit("/", 1)[0] if "/" in dag_s3_path else ""
    return f"{parent}/requirements.txt" if parent else "requirements.txt"


def real_key_for_path(environment: dict, path: str) -> str:
    """Map a Plan's path label to THIS environment's actual S3 key.

    `dags/...` labels other than startup.sh (constraints files, wheels) name
    the real file under DagS3Path, so this needs nothing but the label.
    """
    dag_s3_path = environment.get("DagS3Path", "dags").rstrip("/")

    if path == REQUIREMENTS_PATH:
        return environment.get("RequirementsS3Path") or _default_requirements_key(dag_s3_path)
    if path == DATADOG_REQUIREMENTS_PATH:
        return _default_requirements_key(dag_s3_path).removesuffix("requirements.txt") + "requirements-datadog.txt"
    if path == STARTUP_SCRIPT_PATH:
        return environment.get("StartupScriptS3Path") or f"{dag_s3_path}/startup.sh"
    if path.startswith("dags/"):
        return f"{dag_s3_path}/{path.removeprefix('dags/')}"
    raise ValueError(f"don't know the real S3 key for {path!r}")


class StaleSessionError(RuntimeError):
    """A file the session's plan was computed from has changed since it was scanned."""


def wheel_path(wheel: WheelReference) -> str:
    """A wheel's `dags/...` label -- the same one its file_versions entry uses."""
    return "dags/" + wheel.line.removeprefix(DAGS_MOUNT_PREFIX)


def check_files_unchanged(client: MwaaClient, environment: dict, plan: Plan, file_versions: dict[str, Optional[str]]) -> None:
    """Raise StaleSessionError unless every file the session was scanned from is still that version.

    file_versions is the session's record (see probe.py); this re-reads each
    one's latest VersionId and compares, appearing/disappearing included. It
    also refuses outright if the plan would write a file the session has no
    recorded version for. Called before anything is written.
    """
    written = {fc.path for fc in plan.file_changes} | {wheel_path(fc) for fc in plan.file_changes if isinstance(fc, WheelReference)}
    unrecorded = sorted(written - set(file_versions))
    if unrecorded:
        raise StaleSessionError(f"this session has no recorded version for {', '.join(unrecorded)}. Nothing was written -- re-run scan.")

    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    changed = []
    for path, scanned in file_versions.items():
        try:
            latest = client.latest_version_id(bucket, real_key_for_path(environment, path))
        except (ClientError, VersionIdUnavailable) as exc:
            changed.append(f"{path} (its current version can't be read: {exc})")
            continue
        if latest != scanned:
            changed.append(f"{path} ({scanned or 'missing'} at scan, {latest or 'missing'} now)")
    if changed:
        raise StaleSessionError(f"changed since this session was scanned: {'; '.join(changed)}. Nothing was written -- re-run scan.")


def compute_apply_actions(ctx: ProbeContext, plan: Plan) -> list[FileUpload]:
    """Compute the exact file content to write for every change in a plan.

    plan.file_changes is a flat list of per-package/per-directive/per-variable
    changes, possibly several sharing the same path (e.g. six PinChanges all
    for dags/constraints.txt) -- group by path first, then patch once per file.

    constraints pins are patched into ctx.base_constraints, the full base
    file (see base_constraints.py), never into whatever's at the target key
    or an empty file -- if the base can't be read now, this raises rather
    than produce a pins-only constraints file.

    Everything else is taken from the plan as-is: check_files_unchanged has
    already proven every file it was computed from is still the same version.
    """
    by_path: dict[str, list] = {}
    for change in plan.file_changes:
        by_path.setdefault(change.path, []).append(change)

    uploads = []
    for path, changes in by_path.items():
        old_content = current_text_for_path(ctx, path)
        if _is_constraints_path(path):
            base = ctx.base_constraints
            if base is None or base.text is None:
                raise RuntimeError(f"can't write {path} without its full base constraints file: {base.error if base else 'not resolved'}")
            content = patch_pins(base.text, [c for c in changes if isinstance(c, PinChange)])
            action = "update" if ctx.constraints_text else "create"
        elif path in REQUIREMENTS_PATHS:
            content = patch_pins(old_content, [c for c in changes if isinstance(c, PinChange)])
            content = patch_wheel_references(content, [c for c in changes if isinstance(c, WheelReference)])
            for directive in (c for c in changes if isinstance(c, ConstraintDirectiveChange)):
                content = set_constraint_line(content, directive.to_line)
            action = "update"
        else:  # a startup.sh label -- current_text_for_path already validated the path
            content = patch_env_vars(old_content, [c for c in changes if isinstance(c, EnvVarChange)])
            action = "update" if ctx.startup_script_text else "create"
        uploads.append(FileUpload(path=path, old_content=old_content, content=content, action=action))
    return uploads


def interpolate_api_key(uploads: list[FileUpload], dd_api_key: str) -> list[FileUpload]:
    """Substitute the real Datadog API key into the startup.sh upload's content.

    The only place this happens -- compute_apply_actions (and everything
    upstream of it: Plan, Session) only ever carries DD_API_KEY_PLACEHOLDER.
    Called right before a preview is printed or a file is actually written,
    so the real key exists in memory as briefly as possible and is never
    part of anything persisted or logged.
    """
    return [
        FileUpload(path=u.path, old_content=u.old_content, content=_substitute_api_key(u.content, dd_api_key), action=u.action)
        if u.path in STARTUP_SCRIPT_PATHS
        else u
        for u in uploads
    ]


def apply_to_environment(client: MwaaClient, ctx: ProbeContext, uploads: list[FileUpload], wheels: list[WheelReference]) -> dict[str, Any]:
    """Upload every wheel and file to ITS real S3 key and, if requirements.txt or
    startup.sh changed, call UpdateEnvironment with that same real key.

    Mutating -- an UpdateEnvironment call restarts the environment's workers
    and takes MWAA 20-30 minutes. constraints.txt and wheels alone don't need
    an UpdateEnvironment call: MWAA re-reads the DAGs prefix on every
    install, gated only by the requirements/startup script object versions.

    Every wheel is downloaded before anything is written, so a failed
    download leaves the environment untouched rather than half-applied.
    """
    environment = ctx.environment
    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    uploaded = []
    update_kwargs: dict[str, str] = {}

    wheel_contents = []
    for wheel in wheels:
        content = fetch_bytes(wheel.wheel_url)
        if not content.startswith(b"PK"):
            raise RuntimeError(f"{wheel.wheel_url} didn't return a wheel (zip) file")
        wheel_contents.append((real_key_for_path(environment, wheel_path(wheel)), content))
    for key, content in wheel_contents:
        version_id = client.put_object_bytes(bucket, key, content)
        uploaded.append({"path": key, "version_id": version_id, "action": "create"})

    for upload in uploads:
        real_key = real_key_for_path(environment, upload.path)
        version_id = client.put_object_text(bucket, real_key, upload.content)
        uploaded.append({"path": real_key, "version_id": version_id, "action": upload.action})
        if upload.path in REQUIREMENTS_PATHS:
            update_kwargs["RequirementsS3Path"] = real_key
            if version_id:
                update_kwargs["RequirementsS3ObjectVersion"] = version_id
        elif upload.path in STARTUP_SCRIPT_PATHS:
            update_kwargs["StartupScriptS3Path"] = real_key
            if version_id:
                update_kwargs["StartupScriptS3ObjectVersion"] = version_id

    if update_kwargs:
        client.update_environment(environment["Name"], **update_kwargs)

    return {"uploaded": uploaded, "update_environment_called": bool(update_kwargs)}
