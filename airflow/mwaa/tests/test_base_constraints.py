# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.base_constraints import parse_apache_constraints_url, resolve_base_constraints
from mwaa.fetch import FetchError


def unreachable(url: str) -> bytes:
    raise FetchError(f"could not download {url}: unreachable")


def test_uses_the_2_9_2_python_version_aws_documents():
    fetched = []
    resolve_base_constraints("2.9.2", "", None, "s3://b/dags/constraints.txt", lambda url: fetched.append(url) or b"")

    assert fetched == ["https://raw.githubusercontent.com/apache/airflow/constraints-2.9.2/constraints-3.11.txt"]


def test_unknown_python_version_is_an_error_not_a_guess():
    base = resolve_base_constraints("2.6.3", "", None, "s3://b/dags/constraints.txt", unreachable)

    assert base.text is None
    assert base.source is None
    assert "2.6.3" in base.error


def test_a_local_constraints_path_that_does_not_exist_falls_back_to_upstream():
    requirements = '--constraint "/usr/local/airflow/dags/constraints.txt"\n'
    base = resolve_base_constraints("2.8.1", requirements, None, "s3://b/dags/constraints.txt", lambda url: b"boto3==1.33.13\n")

    assert base.source == "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"
    assert base.text == "boto3==1.33.13\n"


def test_fetch_failure_is_carried_as_an_error():
    base = resolve_base_constraints("2.8.1", "", None, "s3://b/dags/constraints.txt", unreachable)

    assert base.text is None
    assert "unreachable" in base.error


UPSTREAM_2_8_1 = "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"


def requirements_pointing_at(url: str) -> str:
    return f'--constraint "{url}"\n'


def test_a_matching_apache_url_is_used_as_the_base():
    base = resolve_base_constraints("2.8.1", requirements_pointing_at(UPSTREAM_2_8_1), None, "s3://b/x", lambda url: b"boto3==1.33.13\n")

    assert base.source == UPSTREAM_2_8_1
    assert base.text == "boto3==1.33.13\n"


@pytest.mark.parametrize(
    "url, message",
    [
        (
            "https://raw.githubusercontent.com/apache/airflow/constraints-2.7.2/constraints-3.11.txt",
            "--constraint URL is for Airflow 2.7.2 / Python 3.11 but this environment runs Airflow 2.8.1 (Python 3.11); fix the --constraint line and re-scan",
        ),
        (
            "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.10.txt",
            "--constraint URL is for Airflow 2.8.1 / Python 3.10 but this environment runs Airflow 2.8.1 (Python 3.11); fix the --constraint line and re-scan",
        ),
    ],
    ids=["airflow-mismatch", "python-mismatch"],
)
def test_a_mismatched_apache_url_is_an_error_and_is_never_fetched(url, message):
    def fetch(url):
        raise AssertionError("a mismatched URL must not be fetched")

    base = resolve_base_constraints("2.8.1", requirements_pointing_at(url), None, "s3://b/x", fetch)

    assert base.text is None
    assert base.error == message


def test_a_custom_hosted_url_is_used_as_the_base_without_a_version_check():
    url = "https://artifacts.example.com/airflow/constraints-2.7.2/constraints-3.10.txt"
    base = resolve_base_constraints("2.8.1", requirements_pointing_at(url), None, "s3://b/x", lambda url: b"boto3==1.33.13\n")

    assert base.source == url
    assert base.text == "boto3==1.33.13\n"


@pytest.mark.parametrize(
    "url, expected",
    [
        (UPSTREAM_2_8_1, ("2.8.1", "3.11")),
        ("https://RAW.githubusercontent.com/Apache/Airflow/refs/tags/constraints-2.8.1/constraints-3.11.txt", ("2.8.1", "3.11")),
        ("https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-no-providers-3.11.txt", ("2.8.1", "3.11")),
        ("https://raw.githubusercontent.com/apache/airflow/main/constraints-3.11.txt", ("unknown", "3.11")),
        ("https://raw.githubusercontent.com/someone-else/airflow/constraints-2.8.1/constraints-3.11.txt", None),
        ("https://example.com/constraints-2.8.1/constraints-3.11.txt", None),
    ],
)
def test_parse_apache_constraints_url(url, expected):
    assert parse_apache_constraints_url(url) == expected
