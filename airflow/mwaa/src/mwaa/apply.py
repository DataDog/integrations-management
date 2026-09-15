# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Turns a Plan into real file uploads and an MWAA environment update.

Deliberately re-fetches the environment's current files itself (via
ProbeContext, built fresh by discovery/probe) rather than trusting anything
carried in a previously-computed Plan or a persisted scan session -- content
captured during a scan may be stale by the time a plan is reviewed and
applied, and patching against stale content risks clobbering a concurrent
edit. Nothing here is ever printed or persisted outside this process.

REQUIREMENTS_PATH/CONSTRAINTS_PATH/STARTUP_SCRIPT_PATH (plan.py) are internal
labels for what KIND of file a FileChange touches -- never literal S3 keys.
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
from typing import Any

from airflow_shared.mwaa_client import MwaaClient

from .checks import ProbeContext, resolve_constraint_key
from .patch import ensure_constraint_line, patch_pins
from .pins import resolve_constraint_s3_key
from .plan import CONSTRAINTS_PATH, EXPECTED_CONSTRAINT_LINE_TARGET, REQUIREMENTS_PATH, STARTUP_SCRIPT_PATH, FileChange, Plan


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


def _adds_constraint_line(file_change: FileChange) -> bool:
    return any("constraint" in note for note in file_change.notes)


def current_text_for_path(ctx: ProbeContext, path: str) -> str:
    """The real current content for one of the three paths a plan ever touches."""
    if path == CONSTRAINTS_PATH:
        return ctx.constraints_text or ""
    if path == REQUIREMENTS_PATH:
        return ctx.requirements_text
    if path == STARTUP_SCRIPT_PATH:
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


def real_key_for_path(ctx: ProbeContext, path: str) -> str:
    """Map a Plan's generic path label to THIS environment's actual S3 key."""
    dag_s3_path = ctx.environment.get("DagS3Path", "dags")

    if path == REQUIREMENTS_PATH:
        return ctx.environment.get("RequirementsS3Path") or _default_requirements_key(dag_s3_path)
    if path == CONSTRAINTS_PATH:
        existing_key = resolve_constraint_key(ctx.requirements_text, dag_s3_path)
        if existing_key:
            return existing_key
        # No --constraint line yet (first-time "create"): resolve the same
        # target path compute_plan's ensure_constraint_line writes into
        # requirements.txt, so the two agree on where constraints.txt lives.
        return resolve_constraint_s3_key(EXPECTED_CONSTRAINT_LINE_TARGET, dag_s3_path) or f"{dag_s3_path}/constraints.txt"
    if path == STARTUP_SCRIPT_PATH:
        return ctx.environment.get("StartupScriptS3Path") or f"{dag_s3_path}/startup.sh"
    raise ValueError(f"don't know the real S3 key for {path!r}")


def compute_apply_actions(ctx: ProbeContext, plan: Plan) -> list[FileUpload]:
    """Compute the exact file content to write for every change in a plan."""
    uploads = []
    for change in plan.file_changes:
        old_content = current_text_for_path(ctx, change.path)
        if change.path == CONSTRAINTS_PATH:
            content = patch_pins(old_content, change.pin_diff)
        elif change.path == REQUIREMENTS_PATH:
            content = patch_pins(old_content, change.pin_diff)
            if _adds_constraint_line(change):
                content = ensure_constraint_line(content, EXPECTED_CONSTRAINT_LINE_TARGET)
        else:  # STARTUP_SCRIPT_PATH -- current_text_for_path already validated the path
            assert change.content is not None, "startup.sh file changes always carry pre-rendered content"
            content = change.content
        uploads.append(FileUpload(path=change.path, old_content=old_content, content=content, action=change.action))
    return uploads


def apply_to_environment(client: MwaaClient, ctx: ProbeContext, uploads: list[FileUpload]) -> dict[str, Any]:
    """Upload every file to ITS real S3 key and, if requirements.txt or startup.sh
    changed, call UpdateEnvironment with that same real key.

    Mutating -- an UpdateEnvironment call restarts the environment's workers
    and takes MWAA 20-30 minutes. constraints.txt alone doesn't need an
    UpdateEnvironment call: MWAA re-reads it from the DAGs prefix on every
    install, gated only by the requirements/startup script object versions.
    """
    environment = ctx.environment
    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    uploaded = []
    update_kwargs: dict[str, str] = {}

    for upload in uploads:
        real_key = real_key_for_path(ctx, upload.path)
        version_id = client.put_object_text(bucket, real_key, upload.content)
        uploaded.append({"path": real_key, "version_id": version_id, "action": upload.action})
        if upload.path == REQUIREMENTS_PATH:
            update_kwargs["RequirementsS3Path"] = real_key
            if version_id:
                update_kwargs["RequirementsS3ObjectVersion"] = version_id
        elif upload.path == STARTUP_SCRIPT_PATH:
            update_kwargs["StartupScriptS3Path"] = real_key
            if version_id:
                update_kwargs["StartupScriptS3ObjectVersion"] = version_id

    if update_kwargs:
        client.update_environment(environment["Name"], **update_kwargs)

    return {"uploaded": uploaded, "update_environment_called": bool(update_kwargs)}
