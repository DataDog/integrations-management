# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Parsing helpers shared between checks.py and plan.py for requirements.txt / constraints.txt."""

import re

# MWAA mounts the DAGs folder at this path inside the container regardless of
# the S3 prefix (dag_s3_path) the environment is configured with.
DAGS_MOUNT_PREFIX = "/usr/local/airflow/dags/"

OPENLINEAGE_PACKAGES = (
    "apache-airflow-providers-openlineage",
    "openlineage-python",
    "openlineage-integration-common",
    "openlineage-sql",
    "apache-airflow-providers-common-sql",
)
COMMON_COMPAT_PACKAGE = "apache-airflow-providers-common-compat"

CONSTRAINT_LINE = re.compile(r'^\s*--constraint\s+"?([^"\s]+)"?', re.MULTILINE)
_PIN_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-]+)", re.MULTILINE)
# patch_pins' "unpinned" append format (see patch.py) -- a package name alone on its
# line, no version. Anchored at both ends so a `package==version` line's package name
# (which has trailing content after it) never double-matches here too.
_BARE_PACKAGE_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.\-]*)\s*$", re.MULTILINE)


def parse_pins(text: str) -> dict[str, str]:
    """Parse `package==version` lines into a lowercase-keyed dict. Ignores comments and flags."""
    return {name.lower(): version for name, version in _PIN_LINE.findall(text)}


def parse_bare_packages(text: str) -> set[str]:
    """Package names mentioned on their own line with no version pin -- lowercase, like parse_pins.

    Needed alongside parse_pins wherever "is this package already present"
    matters: once patch_pins appends a package unpinned (the unflagged-version
    plan path's target), a plain parse_pins lookup would never find it again,
    and would propose adding it a second time on every subsequent scan.
    """
    return {name.lower() for name in _BARE_PACKAGE_LINE.findall(text)}


def resolve_constraint_s3_key(constraint_path: str, dag_s3_path: str) -> "str | None":
    """Resolve a `--constraint /usr/local/airflow/dags/...` path to an S3 key.

    Returns None if the path isn't under the DAGs mount, which can't be resolved
    back to an S3 object.
    """
    if not constraint_path.startswith(DAGS_MOUNT_PREFIX):
        return None
    relative = constraint_path[len(DAGS_MOUNT_PREFIX) :]
    return f"{dag_s3_path.rstrip('/')}/{relative}"


def find_constraint_path(requirements_text: str) -> "str | None":
    """Return the raw --constraint path from requirements.txt, if present."""
    match = CONSTRAINT_LINE.search(requirements_text)
    return match.group(1) if match else None
