# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Progress/finding reporter for airflow/ cloud-shell tools.

Shaped like gcp_shared.reporter.WorkflowReporter and az_shared.script_status.StatusReporter
(status-per-step, a report() call per transition) so that wiring this up to
Datadog's workflow-status API later -- once an Airflow/MWAA Quickstart exists in
the product -- is a change to the body of `report()` and `report_finding()`
only, not to any call site in mwaa/.

For now, both methods only print to stdout. There is no DD_API_KEY/WORKFLOW_ID
requirement here yet, unlike the gcp/azure quickstarts.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Optional


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    FINISHED = "finished"


class FindingStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


_SYMBOLS = {
    FindingStatus.PASS: "✓",  # check mark
    FindingStatus.WARN: "⚠",  # warning sign
    FindingStatus.FAIL: "✗",  # ballot x
}


@dataclass(frozen=True)
class Finding:
    """The result of one probe check."""

    check_id: str
    status: FindingStatus
    message: str
    detail: Optional[str] = None


class Reporter:
    """Reports step progress and check findings for a probe run."""

    def __init__(self, workflow_type: str):
        self.workflow_type = workflow_type

    def report(self, step: str, status: Status, message: Optional[str] = None) -> None:
        """Report the status of a step. Prints only, for now -- see module docstring."""
        line = f"[{step}] {status.value}"
        if message:
            line += f": {message}"
        print(line)

    @contextmanager
    def report_step(self, step_id: str) -> Generator[None, None, None]:
        """Report the start and outcome of a step."""
        self.report(step_id, Status.IN_PROGRESS)
        try:
            yield
        except Exception as e:
            self.report(step_id, Status.FAILED, message=str(e))
            raise
        else:
            self.report(step_id, Status.FINISHED)

    def report_finding(self, finding: Finding) -> None:
        """Report one probe check's finding. Prints only, for now -- see module docstring."""
        symbol = _SYMBOLS[finding.status]
        print(f"  {symbol} [{finding.check_id}] {finding.message}")
        if finding.detail:
            for line in finding.detail.strip().split("\n"):
                print(f"      {line}")

    def summary(self, findings: list[Finding]) -> None:
        """Print a pass/warn/fail summary line for a full probe run."""
        counts = {status: 0 for status in FindingStatus}
        for finding in findings:
            counts[finding.status] += 1
        print()
        print(
            f"Probe complete: {counts[FindingStatus.PASS]} passed, "
            f"{counts[FindingStatus.WARN]} warned, {counts[FindingStatus.FAIL]} failed."
        )
