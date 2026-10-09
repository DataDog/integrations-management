# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from airflow_shared.mwaa_client import ObjectNotFoundError
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


class FakeS3Client:
    """Just enough of MwaaClient to build a context from, apply against and re-check.

    Backed by a dict of key -> content, with a fresh VersionId per write.
    Keys in `unreadable` answer HeadObject with a 403, like a missing key
    without s3:ListBucket.
    """

    def __init__(self, environment: dict, objects: dict, unreadable: frozenset = frozenset()):
        self.environment = dict(environment)
        self.objects = dict(objects)
        self.versions = {key: f"v-{key}-0" for key in objects}
        self.unreadable = unreadable
        # like MWAA, UpdateEnvironment repoints the environment at the files it names
        self.update_environment = MagicMock(side_effect=lambda name, **kwargs: self.environment.update(kwargs))

    def get_environment(self, name):
        return self.environment

    def get_object_text(self, bucket, key, version_id=None):
        if key not in self.objects:
            raise ObjectNotFoundError(key)
        return self.objects[key]

    def put_object_text(self, bucket, key, content):
        return self.put_object_bytes(bucket, key, content)

    def put_object_bytes(self, bucket, key, content):
        self.objects[key] = content
        self.versions[key] = f"v-{key}-{int(self.versions.get(key, 'v--1').rsplit('-', 1)[-1]) + 1}"
        return self.versions[key]

    def object_exists(self, bucket, key):
        return key in self.objects

    def latest_version_id(self, bucket, key):
        if key in self.unreadable:
            raise ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")
        return self.versions.get(key)

    def simulate_s3_read_access(self, role_arn, bucket_arn):
        return {"s3:GetObject": True, "s3:ListBucket": True}
