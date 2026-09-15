# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.pins import parse_bare_packages, parse_pins


def test_parse_bare_packages_finds_unpinned_lines():
    text = "pandas==2.1.4\napache-airflow-providers-openlineage\nboto3==1.34.11\n"
    assert parse_bare_packages(text) == {"apache-airflow-providers-openlineage"}


def test_parse_bare_packages_ignores_pinned_lines():
    assert parse_bare_packages("pandas==2.1.4\n") == set()


def test_parse_bare_packages_ignores_comments_and_flags():
    text = "# a comment\n--constraint /usr/local/airflow/dags/constraints.txt\npandas==2.1.4\n"
    assert parse_bare_packages(text) == set()


def test_parse_bare_packages_is_lowercase_like_parse_pins():
    text = "Apache-Airflow-Providers-Openlineage\n"
    assert parse_bare_packages(text) == {"apache-airflow-providers-openlineage"}
    assert parse_pins(text) == {}
