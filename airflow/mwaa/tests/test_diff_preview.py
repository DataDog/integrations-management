# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.diff_preview import render_unified_diff


def test_render_unified_diff_shows_changed_line():
    diff = render_unified_diff(
        "requirements.txt",
        "apache-airflow-providers-openlineage==1.4.0\n",
        "apache-airflow-providers-openlineage==1.14.0\n",
    )
    assert "-apache-airflow-providers-openlineage==1.4.0" in diff
    assert "+apache-airflow-providers-openlineage==1.14.0" in diff
    assert "a/requirements.txt" in diff
    assert "b/requirements.txt" in diff


def test_render_unified_diff_empty_for_identical_content():
    assert render_unified_diff("f.txt", "same\n", "same\n") == ""


def test_render_unified_diff_shows_new_file_as_all_additions():
    diff = render_unified_diff("dags/startup.sh", "", "#!/bin/sh\necho hi\n")
    assert "+#!/bin/sh" in diff
    assert "+echo hi" in diff
