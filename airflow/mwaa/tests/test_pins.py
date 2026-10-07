# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.pins import find_wheel_references, mentions_package


def test_mentions_package_finds_a_bare_line():
    assert mentions_package("pandas==2.1.4\napache-airflow-providers-openlineage\n", "apache-airflow-providers-openlineage")


def test_mentions_package_finds_pinned_and_ranged_lines_case_insensitively():
    assert mentions_package("Apache-Airflow-Providers-OpenLineage==1.4.0\n", "apache-airflow-providers-openlineage")
    assert mentions_package("apache-airflow-providers-openlineage>=1.4.0\n", "apache-airflow-providers-openlineage")


def test_mentions_package_finds_a_wheel_reference():
    text = "/usr/local/airflow/dags/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl\n"
    assert mentions_package(text, "apache-airflow-providers-openlineage")


def test_mentions_package_ignores_similarly_named_packages_comments_and_flags():
    text = (
        "# apache-airflow-providers-openlineage\n"
        "--constraint /usr/local/airflow/dags/constraints.txt\n"
        "apache-airflow-providers-openlineage-extra==1.0\n"
    )
    assert not mentions_package(text, "apache-airflow-providers-openlineage")


def test_find_wheel_references_finds_local_dags_mount_path():
    text = "pandas==2.1.4\n/usr/local/airflow/dags/wheels/datadog_provider-1.0.0-py3-none-any.whl\n"
    assert find_wheel_references(text) == ["/usr/local/airflow/dags/wheels/datadog_provider-1.0.0-py3-none-any.whl"]


def test_find_wheel_references_ignores_comments():
    text = "# /usr/local/airflow/dags/wheels/old.whl\npandas==2.1.4\n"
    assert find_wheel_references(text) == []


def test_find_wheel_references_empty_when_none_referenced():
    assert find_wheel_references("pandas==2.1.4\n") == []
