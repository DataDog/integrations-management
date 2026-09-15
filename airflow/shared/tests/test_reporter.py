# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from airflow_shared.reporter import Finding, FindingStatus, Reporter


@pytest.fixture
def reporter() -> Reporter:
    return Reporter(workflow_type="mwaa-setup")


def test_report_step_prints_in_progress_then_finished(reporter: Reporter, capsys):
    with reporter.report_step("probe"):
        pass
    out = capsys.readouterr().out
    assert "[probe] in_progress" in out
    assert "[probe] finished" in out


def test_report_step_prints_failed_and_reraises(reporter: Reporter, capsys):
    with pytest.raises(RuntimeError):
        with reporter.report_step("probe"):
            raise RuntimeError("boom")
    out = capsys.readouterr().out
    assert "[probe] failed: boom" in out


def test_report_finding_prints_symbol_and_detail(reporter: Reporter, capsys):
    reporter.report_finding(
        Finding(check_id="constraint_path", status=FindingStatus.FAIL, message="missing", detail="line 1\nline 2")
    )
    out = capsys.readouterr().out
    assert "[constraint_path] missing" in out
    assert "line 1" in out
    assert "line 2" in out


def test_summary_counts_each_status(reporter: Reporter, capsys):
    findings = [
        Finding(check_id="a", status=FindingStatus.PASS, message=""),
        Finding(check_id="b", status=FindingStatus.WARN, message=""),
        Finding(check_id="c", status=FindingStatus.FAIL, message=""),
        Finding(check_id="d", status=FindingStatus.PASS, message=""),
    ]
    reporter.summary(findings)
    out = capsys.readouterr().out
    assert "2 passed, 1 warned, 1 failed" in out
