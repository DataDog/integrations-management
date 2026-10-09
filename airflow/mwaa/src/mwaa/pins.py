# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Parsing helpers shared between checks.py and plan.py for requirements.txt / constraints.txt."""

import re

# MWAA mounts the DAGs folder at this path inside the container regardless of
# the S3 prefix (dag_s3_path) the environment is configured with.
DAGS_MOUNT_PREFIX = "/usr/local/airflow/dags/"
OPENLINEAGE_PROVIDER = "apache-airflow-providers-openlineage"

CONSTRAINT_LINE = re.compile(r'^\s*(?:--constraint|-c)(?:\s+|=)"?([^"\s]+)"?', re.MULTILINE)
WHEEL_REFERENCE = re.compile(r"(\S+\.whl)")
_PIN_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-]+)", re.MULTILINE)
_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


def normalize_package_name(name: str) -> str:
    """PEP 503 normalization, the way pip compares project names.

    Upstream constraints files spell some projects with underscores
    (`openlineage_sql==1.3.1`), so a literal-name comparison would miss them
    and end up with two conflicting lines for one project.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def stale_pin(text: str, package: str, target: str) -> "tuple[bool, str | None]":
    """(needs a change, the version to show it changing from) for one package's pins in `text`.

    A project pinned on more than one line (upstream constraints spell some
    with underscores, so a patched file can end up with both) only counts as
    at `target` if every one of its pins is -- pip enforces them all.
    """
    versions = [version for name, version in _PIN_LINE.findall(text) if normalize_package_name(name) == package]
    stale = [version for version in versions if version != target]
    if versions and not stale:
        return False, None
    return True, stale[0] if stale else None


def wheel_identity(filename: str) -> tuple[str, str]:
    """(normalized project name, version) from a wheel filename, so two spellings of one wheel compare equal."""
    name, _, rest = filename.partition("-")
    return normalize_package_name(name), rest.split("-", 1)[0]


def requirement_line_package(line: str) -> "str | None":
    """The package one requirements.txt line installs, normalized (lowercase, `-` separators).

    Covers every form a line can name a package in -- `pkg==1.0`, `pkg>=1.0`,
    a bare `pkg` (patch_pins' to_version=None output), or a wheel file path,
    whose filename starts with the distribution name. None for comments,
    blank lines and `--flag` lines.
    """
    stripped = line.split("#", 1)[0].strip()
    if not stripped or stripped.startswith("-"):
        return None
    wheel = WHEEL_REFERENCE.search(stripped)
    if wheel:
        return normalize_package_name(wheel.group(1).rsplit("/", 1)[-1].split("-", 1)[0])
    match = _REQUIREMENT_NAME.match(stripped)
    return normalize_package_name(match.group(0)) if match else None


def mentions_package(requirements_text: str, package: str) -> bool:
    """Whether any requirements.txt line installs `package`, in any of requirement_line_package's forms.

    A `==` lookup alone isn't enough wherever "is this package already present"
    matters: once patch_pins appends a package unpinned (the unflagged-version
    plan path's target), it would never find it again, and would propose
    adding it a second time on every subsequent scan.
    """
    return any(requirement_line_package(line) == normalize_package_name(package) for line in requirements_text.splitlines())


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


def find_constraint_lines(requirements_text: str) -> list[str]:
    """Return every whole --constraint/-c line in requirements.txt, stripped, in order.

    pip enforces every one of them, not just the first -- see plan.py's
    handling of more than one.
    """
    return [line.strip() for line in requirements_text.splitlines() if CONSTRAINT_LINE.match(line)]


def find_wheel_references(requirements_text: str) -> list[str]:
    """Return every .whl path referenced in requirements.txt, in order.

    Airflow 2.7.2's documented upgrade path requires uploading Datadog-patched
    wheels by hand; a customer who renames or forgets one produces a plain
    S3 path reference here, not a package pin.
    """
    refs = []
    for line in requirements_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = WHEEL_REFERENCE.search(stripped)
        if match:
            refs.append(match.group(1))
    return refs
