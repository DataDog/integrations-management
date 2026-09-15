# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Turns a Plan into real file uploads and an MWAA environment update.

Deliberately re-fetches the environment's current files itself (via
ProbeContext, built fresh by discovery/probe) rather than trusting anything
carried in a previously-computed Plan or a persisted scan payload -- content
captured during a scan may be stale by the time a plan is reviewed and
applied, and patching against stale content risks clobbering a concurrent
edit. Nothing here is ever printed or persisted outside this process.
"""

from dataclasses import dataclass
from typing import Any

from airflow_shared.mwaa_client import MwaaClient

from .checks import ProbeContext
from .patch import ensure_constraint_line, patch_pins
from .plan import CONSTRAINTS_PATH, EXPECTED_CONSTRAINT_LINE_TARGET, REQUIREMENTS_PATH, STARTUP_SCRIPT_PATH, FileChange, Plan


@dataclass(frozen=True)
class FileUpload:
    """One file's final content, ready to write to S3."""

    path: str
    content: str
    action: str  # "create" | "update"


def _adds_constraint_line(file_change: FileChange) -> bool:
    return any("constraint" in note for note in file_change.notes)


def compute_apply_actions(ctx: ProbeContext, plan: Plan) -> list[FileUpload]:
    """Compute the exact file content to write for every change in a plan."""
    uploads = []
    for change in plan.file_changes:
        if change.path == CONSTRAINTS_PATH:
            content = patch_pins(ctx.constraints_text or "", change.pin_diff)
        elif change.path == REQUIREMENTS_PATH:
            content = patch_pins(ctx.requirements_text, change.pin_diff)
            if _adds_constraint_line(change):
                content = ensure_constraint_line(content, EXPECTED_CONSTRAINT_LINE_TARGET)
        elif change.path == STARTUP_SCRIPT_PATH:
            assert change.content is not None, "startup.sh file changes always carry pre-rendered content"
            content = change.content
        else:
            raise ValueError(f"don't know how to apply a change to {change.path!r}")
        uploads.append(FileUpload(path=change.path, content=content, action=change.action))
    return uploads


def apply_to_environment(client: MwaaClient, environment: dict[str, Any], uploads: list[FileUpload]) -> dict[str, Any]:
    """Upload every file and, if requirements.txt or startup.sh changed, call UpdateEnvironment.

    Mutating -- an UpdateEnvironment call restarts the environment's workers
    and takes MWAA 20-30 minutes. constraints.txt alone doesn't need an
    UpdateEnvironment call: MWAA re-reads it from the DAGs prefix on every
    install, gated only by the requirements/startup script object versions.
    """
    bucket = environment["SourceBucketArn"].rsplit(":", 1)[-1]
    uploaded = []
    update_kwargs: dict[str, str] = {}

    for upload in uploads:
        version_id = client.put_object_text(bucket, upload.path, upload.content)
        uploaded.append({"path": upload.path, "version_id": version_id, "action": upload.action})
        if upload.path == REQUIREMENTS_PATH:
            update_kwargs["RequirementsS3Path"] = upload.path
            if version_id:
                update_kwargs["RequirementsS3ObjectVersion"] = version_id
        elif upload.path == STARTUP_SCRIPT_PATH:
            update_kwargs["StartupScriptS3Path"] = upload.path
            if version_id:
                update_kwargs["StartupScriptS3ObjectVersion"] = version_id

    if update_kwargs:
        client.update_environment(environment["Name"], **update_kwargs)

    return {"uploaded": uploaded, "update_environment_called": bool(update_kwargs)}
