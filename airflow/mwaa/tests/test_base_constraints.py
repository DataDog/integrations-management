# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from mwaa.base_constraints import resolve_base_constraints
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
