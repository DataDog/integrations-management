# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Callable
from dataclasses import dataclass, field

from az_shared.logs import log, log_header


def _noop() -> None:
    pass


@dataclass
class Step:
    """A single unit of migration work with a corresponding rollback action."""

    name: str
    execute: Callable[[], None]
    rollback: Callable[[], None] = field(default=_noop)


def run_steps(steps: list[Step]) -> None:
    """Run steps in order. If a step fails, its own rollback is run first, then the
    rollback actions of all preceding (completed) steps are run in reverse order, and
    the original error is re-raised. A rollback failure is logged but does not prevent
    the remaining rollbacks from running.
    """
    completed_steps: list[Step] = []

    for curr_step in steps:
        log_header(f"STEP: {curr_step.name}")
        try:
            curr_step.execute()
        except Exception as e:
            log.error(f"Step '{curr_step.name}' failed: {e}")
            _safe_rollback(curr_step)
            _rollback_completed_steps(completed_steps)
            raise
        completed_steps.append(curr_step)


def _rollback_completed_steps(completed: list[Step]) -> None:
    if not completed:
        return
    log.error("Rolling back preceding steps...")
    for step in reversed(completed):
        _safe_rollback(step)


def _safe_rollback(step: Step) -> None:
    try:
        log.info(f"Rolling back step: {step.name}")
        step.rollback()
    except Exception as rollback_error:
        log.error(f"Rollback for step '{step.name}' failed: {rollback_error}")
