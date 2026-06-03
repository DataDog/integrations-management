# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Top-level state machine: run all 5 phases for a single control plane."""

from az_shared.logs import log, log_header

from .discovery import ControlPlane
from .phases.cleanup import cleanup_steps
from .phases.create_jobs import create_paused_jobs_steps
from .phases.enable import enablement_steps
from .phases.roles import assign_roles_steps
from .phases.setup import build_context
from .preflight import assert_permissions
from .steps import Runner


def migrate_control_plane(cp: ControlPlane) -> list[str]:
    """Migrate a single control plane. Returns the manual-action list collected
    during Phase 5 (always empty if the cleanup phase completed cleanly)."""

    log_header(f"Migrating control plane '{cp.control_plane_id}' in subscription {cp.sub_id}")

    log_header("Phase 1: discovery")
    ctx = build_context(cp)

    log_header("Phase 1.5: permission preflight")
    assert_permissions(ctx)

    runner = Runner()

    log_header("Phase 2: create paused Container App Jobs")
    for step in create_paused_jobs_steps(ctx):
        runner.run(step)

    log_header("Phase 3: assign roles")
    for step in assign_roles_steps(ctx):
        runner.run(step)

    log_header("Phase 4: enablement")
    for step in enablement_steps(ctx):
        runner.run(step)

    log_header("Phase 5: cleanup (best-effort)")
    for step, hint in cleanup_steps(ctx):
        runner.run_best_effort(step, hint)

    if runner.manual_actions:
        log.warning("Cleanup left manual actions for this control plane:")
        for action in runner.manual_actions:
            log.warning(f"  - {action}")
    else:
        log.info("Control plane migration completed cleanly")

    return list(runner.manual_actions)
