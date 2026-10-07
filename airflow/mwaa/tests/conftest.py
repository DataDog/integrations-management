# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import pytest

from mwaa.fetch import FetchError

UPSTREAM_2_8_1_URL = "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"

# a trimmed stand-in for the real upstream file: the openlineage pins it actually
# carries for 2.8.1, spelled the way it spells them (openlineage_sql), plus enough
# unrelated pins to tell "full base" from "pins only"
UPSTREAM_2_8_1_TEXT = (
    "# This constraints file was automatically generated\n"
    "apache-airflow-providers-amazon==8.16.0\n"
    "apache-airflow-providers-common-sql==1.10.0\n"
    "apache-airflow-providers-openlineage==1.4.0\n"
    "boto3==1.33.13\n"
    "openlineage-integration-common==1.7.0\n"
    "openlineage-python==1.7.0\n"
    "openlineage_sql==1.7.0\n"
    "pandas==2.1.4\n"
)

UPSTREAM_2_7_2_URL = "https://raw.githubusercontent.com/apache/airflow/constraints-2.7.2/constraints-3.11.txt"
UPSTREAM_2_7_2_TEXT = (
    "apache-airflow-providers-common-sql==1.7.2\n"
    "apache-airflow-providers-openlineage==1.1.0\n"
    "boto3==1.28.62\n"
    "openlineage_sql==1.3.1\n"
)

OPENLINEAGE_WHEEL_URL = "https://docs.datadoghq.com/resources/whl/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl"
COMMON_COMPAT_WHEEL_URL = "https://docs.datadoghq.com/resources/whl/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl"
FAKE_WHEEL_BYTES = b"PK\x03\x04 not really a wheel"


@pytest.fixture(autouse=True)
def fake_fetch(monkeypatch) -> dict[str, bytes]:
    """Stands in for every HTTPS fetch, so no test ever reaches the network.

    Maps URL -> body; tests add, replace or delete entries. Anything not in
    it raises FetchError, the same as an unreachable host.
    """
    responses = {
        UPSTREAM_2_8_1_URL: UPSTREAM_2_8_1_TEXT.encode(),
        UPSTREAM_2_7_2_URL: UPSTREAM_2_7_2_TEXT.encode(),
        OPENLINEAGE_WHEEL_URL: FAKE_WHEEL_BYTES,
        COMMON_COMPAT_WHEEL_URL: FAKE_WHEEL_BYTES,
    }

    def fetch(url: str, timeout: float = 30.0) -> bytes:
        if url not in responses:
            raise FetchError(f"could not download {url}: not stubbed")
        return responses[url]

    monkeypatch.setattr("mwaa.probe.fetch_bytes", fetch)
    monkeypatch.setattr("mwaa.apply.fetch_bytes", fetch)
    return responses
