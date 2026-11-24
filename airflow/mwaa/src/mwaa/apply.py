# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Turns a Plan into real file uploads and an MWAA environment update.

A session never carries file content, so the files are re-fetched here (via
ProbeContext, built fresh by probe) to patch against. check_files_unchanged
first proves each one is still the exact S3 version the plan was computed
from -- anything changed means re-scan, never patch -- so the plan itself is
applied as-is. Nothing here is ever printed or persisted outside this process.

A session's plan and file_versions name each file by its real S3 key (see
session.py). Which file a key is -- requirements.txt, the constraints file,
startup.sh -- comes from mapping ctx's labels through real_key_for_path
(plan.py) again, so a key the environment no longer uses is a stale session,
never a guess. Writing to anything but that real key once bit a real
environment: one whose RequirementsS3Path lived under a `setup-probe/<name>/`
prefix got its upload sent to the literal key "requirements.txt" -- a
different environment's real file, in the same bucket.
"""

from dataclasses import dataclass, replace
from typing import Any, Optional

from airflow_shared.mwaa_client import MwaaClient, VersionIdUnavailable

from botocore.exceptions import ClientError

from .checks import ProbeContext
from .fetch import fetch_bytes
from .openlineage_config import merge_transport_fields
from .patch import patch_env_vars, patch_pins, patch_wheel_references, set_constraint_line
from .plan import (
    REQUIREMENTS_PATHS,
    STARTUP_SCRIPT_PATHS,
    ConstraintDirectiveChange,
    EnvVarChange,
    PinChange,
    Plan,
    WheelReference,
    real_key_for_path,
    wheel_path,
)
from .startup_script import interpolate_api_key as _substitute_api_key


@dataclass(frozen=True)
class FileUpload:
    """One file's final content, ready to write to S3, alongside what it's replacing.

    `path` is the real S3 key it's written to; `label` is which plan.py file it
    is (REQUIREMENTS_PATH etc.), which decides how it's patched and deployed.
    """

    path: str
    label: str
    old_content: str
    content: str
    action: str  # "create" | "update"


class StaleSessionError(RuntimeError):
    """A file the session's plan was computed from has changed since it was scanned."""


def plan_file_labels(ctx: ProbeContext) -> dict[str, str]:
    """Real S3 key -> plan.py label for the files a plan can write in this environment, as ctx sees it now."""
    labels = [ctx.requirements_path, ctx.startup_script_path, ctx.constraints_path]
    return {real_key_for_path(ctx.environment, label): label for label in labels}


def _is_constraints_path(path: str) -> bool:
    """Every `dags/...` label a plan uses other than startup.sh names its constraints file."""
    return path not in STARTUP_SCRIPT_PATHS and path.startswith("dags/")


def current_text_for_path(ctx: ProbeContext, path: str) -> str:
    """The real current content for one of the three files a plan ever touches, by its plan.py label."""
    if _is_constraints_path(path):
        return ctx.constraints_text or ""
    if path in REQUIREMENTS_PATHS:
        return ctx.requirements_target_text if ctx.requirements_target_text is not None else ctx.requirements_text
    if path in STARTUP_SCRIPT_PATHS:
        return (ctx.startup_script_target_text if ctx.startup_script_target_text is not None else ctx.startup_script_text) or ""
    raise ValueError(f"don't know how to apply a change to {path!r}")


def check_files_unchanged(client: MwaaClient, environment: dict, plan: Plan, file_versions: dict[str, Optional[str]]) -> None:
    """Raise StaleSessionError unless every file the session was scanned from is still that version.

    file_versions is the session's record (see probe.py), keyed by real S3
    key; this re-reads each one's latest VersionId and compares,
    appearing/disappearing included. It also refuses outright if the plan
    would write a file the session has no recorded version for. Called before
    anything is written.
    """
    written = {fc.path for fc in plan.file_changes} | {
        real_key_for_path(environment, wheel_path(fc)) for fc in plan.file_changes if isinstance(fc, WheelReference)
    }
    unrecorded = sorted(written - set(file_versions))
    if unrecorded:
        raise StaleSessionError(f"this session has no recorded version for {', '.join(unrecorded)}. Nothing was written -- re-run scan.")

    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    changed = []
    for path, scanned in file_versions.items():
        try:
            latest = client.latest_version_id(bucket, path)
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
    for the constraints file) -- group by path first, then patch once per file.
    A path that isn't one of the files this environment's plan can write (see
    plan_file_labels) means the session no longer matches it.

    constraints pins are patched into ctx.base_constraints (see
    base_constraints.py), never into whatever's at the target key -- if the
    --constraint file it comes from can't be read now, this raises rather
    than write a file the plan wasn't computed against.

    Everything else is taken from the plan as-is: check_files_unchanged has
    already proven every file it was computed from is still the same version.
    """
    by_path: dict[str, list] = {}
    for change in plan.file_changes:
        by_path.setdefault(change.path, []).append(change)

    labels = plan_file_labels(ctx)
    unknown = sorted(set(by_path) - set(labels))
    if unknown:
        raise StaleSessionError(f"this session's plan writes {', '.join(unknown)}, which this environment doesn't use now. Nothing was written -- re-run scan.")

    uploads = []
    for path, changes in by_path.items():
        label = labels[path]
        old_content = current_text_for_path(ctx, label)
        if _is_constraints_path(label):
            base = ctx.base_constraints
            if base is None or base.text is None:
                raise RuntimeError(f"can't write {path} without its full base constraints file: {base.error if base else 'not resolved'}")
            content = patch_pins(base.text, [c for c in changes if isinstance(c, PinChange)])
            action = "update" if ctx.constraints_text else "create"
        elif label in REQUIREMENTS_PATHS:
            content = patch_pins(old_content, [c for c in changes if isinstance(c, PinChange)])
            content = patch_wheel_references(content, [c for c in changes if isinstance(c, WheelReference)])
            for directive in (c for c in changes if isinstance(c, ConstraintDirectiveChange)):
                content = set_constraint_line(content, directive.to_line)
            action = "update"
        else:  # a startup.sh label -- current_text_for_path already validated it
            env_var_changes = [_with_transport_merged(c, old_content) for c in changes if isinstance(c, EnvVarChange)]
            content = patch_env_vars(old_content, env_var_changes)
            action = "update" if old_content else "create"
        uploads.append(FileUpload(path=path, label=label, old_content=old_content, content=content, action=action))
    return uploads


def _with_transport_merged(change: EnvVarChange, startup_script_text: str) -> EnvVarChange:
    """A TRANSPORT change only carries the fields it sets (see openlineage_config.py); the rest
    of the transport, which may hold credentials, comes from the file as it is now."""
    if change.name != "AIRFLOW__OPENLINEAGE__TRANSPORT":
        return change
    merged = merge_transport_fields(startup_script_text, change.to_value)
    if merged is None:
        raise StaleSessionError("the startup script's AIRFLOW__OPENLINEAGE__TRANSPORT isn't a JSON object any more. Nothing was written -- re-run scan.")
    return replace(change, to_value=merged)


def interpolate_api_key(uploads: list[FileUpload], dd_api_key: str) -> list[FileUpload]:
    """Substitute the real Datadog API key into the startup.sh upload's content.

    The only place this happens -- compute_apply_actions (and everything
    upstream of it: Plan, Session) only ever carries DD_API_KEY_PLACEHOLDER.
    Called right before a preview is printed or a file is actually written,
    so the real key exists in memory as briefly as possible and is never
    part of anything persisted or logged.
    """
    return [
        replace(u, content=_substitute_api_key(u.content, dd_api_key))
        if u.label in STARTUP_SCRIPT_PATHS
        else u
        for u in uploads
    ]


def apply_to_environment(client: MwaaClient, ctx: ProbeContext, uploads: list[FileUpload], wheels: list[WheelReference]) -> dict[str, Any]:
    """Upload every wheel and file to its real S3 key and, if requirements.txt or
    startup.sh changed, call UpdateEnvironment with that same key.

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
        version_id = client.put_object_text(bucket, upload.path, upload.content)
        uploaded.append({"path": upload.path, "version_id": version_id, "action": upload.action})
        if upload.label in REQUIREMENTS_PATHS:
            update_kwargs["RequirementsS3Path"] = upload.path
            if version_id:
                update_kwargs["RequirementsS3ObjectVersion"] = version_id
        elif upload.label in STARTUP_SCRIPT_PATHS:
            update_kwargs["StartupScriptS3Path"] = upload.path
            if version_id:
                update_kwargs["StartupScriptS3ObjectVersion"] = version_id

    if update_kwargs:
        client.update_environment(environment["Name"], **update_kwargs)

    return {"uploaded": uploaded, "update_environment_called": bool(update_kwargs)}
