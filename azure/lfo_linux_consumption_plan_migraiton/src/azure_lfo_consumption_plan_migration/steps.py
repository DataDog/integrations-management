# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from az_shared.logs import log


@dataclass
class Step:
    """A single forward action with its optional rollback.

    `do` is called when running the step. If it succeeds the step is pushed
    onto the runner's rollback stack. If a later step fails, the runner pops
    each previously-completed step and invokes its `undo`.

    `undo=None` opts the step out of rollback - used by Phase 5 cleanup, where
    individual failures are collected into a manual-action report rather than
    triggering rollback.
    """

    name: str
    do: Callable[[], None]
    undo: Optional[Callable[[], None]] = None


class RollbackError(RuntimeError):
    """Raised after the runner has finished unwinding completed steps so the
    caller can distinguish 'rollback completed' from a bare exception.
    """


class Runner:
    """Executes a sequence of `Step`s with stack-based rollback on failure."""

    def __init__(self) -> None:
        self._completed: list[Step] = []
        self.manual_actions: list[str] = []

    def run(self, step: Step) -> None:
        log.info(f"  -> {step.name}")
        try:
            step.do()
        except Exception as e:
            log.error(f"Step '{step.name}' failed: {e}")
            self._rollback()
            raise RollbackError(f"Aborted at step '{step.name}': {e}") from e
        if step.undo is not None:
            self._completed.append(step)

    def run_best_effort(self, step: Step, manual_action_hint: str) -> None:
        """Phase-5-style: never rolls back; collects a manual-action message
        on failure so the customer can fix the leftover state by hand."""
        log.info(f"  -> {step.name}")
        try:
            step.do()
        except Exception as e:
            log.warning(f"Step '{step.name}' failed (continuing): {e}")
            self.manual_actions.append(f"{step.name}: {manual_action_hint} (error: {e})")

    def _rollback(self) -> None:
        if not self._completed:
            return
        log.warning("Rolling back completed steps...")
        while self._completed:
            step = self._completed.pop()
            if step.undo is None:
                continue
            try:
                log.info(f"  <- undo: {step.name}")
                step.undo()
            except Exception as e:
                log.error(f"Rollback of '{step.name}' failed: {e}")
                self.manual_actions.append(
                    f"Rollback of '{step.name}' failed - manual intervention may be required (error: {e})"
                )
