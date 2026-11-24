# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Which constraints file a flagged version's OpenLineage pins get patched into.

When requirements.txt already has a --constraint line, the environment's other
packages already resolve against that file, so the pins are patched into it:

  1. the local constraints file requirements.txt points at under the DAGs
     mount (it's patched in place, whatever it's named);
  2. the https:// URL requirements.txt's --constraint line points at (plain
     http:// is refused: its content can't be trusted) -- most often the
     upstream file itself, which is what AWS recommends. When it's an
     Apache-hosted upstream file, its Airflow/Python versions must match the
     environment's (see parse_apache_constraints_url); a custom-hosted file
     is used as-is.

When the file a --constraint line references can't be read (it doesn't exist,
isn't under the DAGs mount or https://, can't be downloaded, ...), there's no
safe file to write -- its other pins may still be in force -- so `text` is None
and plan.py leaves the package changes out entirely (see
check_base_constraints for the issue that records why).

  3. With no --constraint line at all, the file written mirrors what MWAA
     already applies, plus the OpenLineage pins -- per version, see
     FlaggedVersionEntry.mwaa_forces_upstream_constraints:
     - where MWAA forces the upstream constraints-<v>/constraints-<py>.txt
       itself (2.7.2, 2.9.2), that same file. A minimal one would switch the
       forcing off and let every unpinned package float to its latest
       release (pandas 2 -> 3, numpy 1 -> 2). When it can't be downloaded,
       `text` is None, the same as cases 1 and 2.
     - where MWAA applies none (2.8.1), MINIMAL_CONSTRAINTS_HEADER plus just
       the OpenLineage pins. The full upstream file there would newly enforce
       its old pins, and a customer's newer one (boto3, say) would make pip
       refuse all of requirements.txt -- while MWAA still reports success.
     MWAA installs apache-airflow==<version> as a top-level requirement
     itself, so Airflow stays pinned either way.
"""

import re
import urllib.parse
from dataclasses import dataclass, replace
from typing import Callable, Optional

from .fetch import FetchError
from .pins import DAGS_MOUNT_PREFIX, find_constraint_path
from .version_table import FLAGGED_VERSION_TABLE, PYTHON_VERSION_BY_AIRFLOW_VERSION, UPSTREAM_CONSTRAINTS_URL


@dataclass(frozen=True)
class BaseConstraints:
    source: Optional[str]  # an s3:// URI or https URL; None if not even a source could be determined
    text: Optional[str]  # None when it couldn't be read -- see error
    error: Optional[str] = None
    minimal: bool = False  # case 3 where MWAA forces nothing: just the header the pins get appended to
    mwaa_default: bool = False  # case 3 where MWAA forces the upstream file: that file, which it already applies


MINIMAL_CONSTRAINTS_HEADER = (
    "# Pins only the OpenLineage packages Datadog Data Observability needs; MWAA applies no constraints of its own on this "
    "Airflow version, so every other package resolves as it did before.\n"
)


_APACHE_CONSTRAINTS_REF = re.compile(r"constraints-(.+)")
# upstream also publishes constraints-no-providers-<py>.txt / constraints-source-providers-<py>.txt
_APACHE_CONSTRAINTS_FILE = re.compile(r"constraints-(?:[a-z]+(?:-[a-z]+)*-)?(\d+\.\d+)\.txt")


def parse_apache_constraints_url(url: str) -> "tuple[str, str] | None":
    """(airflow_version, python_version) an Apache-hosted upstream constraints URL is for.

    None if the URL isn't raw.githubusercontent.com/apache/airflow at all.
    Either half is "unknown" if the URL is Apache-hosted but doesn't name it
    the usual way (e.g. a branch ref), which can't match any environment.
    Tolerates a `refs/tags/` or `refs/heads/` ref prefix.
    """
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if (parsed.hostname or "").lower() != "raw.githubusercontent.com" or [p.lower() for p in parts[:2]] != ["apache", "airflow"]:
        return None
    ref = _APACHE_CONSTRAINTS_REF.fullmatch(parts[-2]) if len(parts) >= 4 else None
    filename = _APACHE_CONSTRAINTS_FILE.fullmatch(parts[-1]) if len(parts) >= 4 else None
    return (ref.group(1) if ref else "unknown", filename.group(1) if filename else "unknown")


def resolve_base_constraints(
    airflow_version: str,
    requirements_text: str,
    local_constraints_text: Optional[str],
    local_constraints_uri: str,
    fetch: Callable[[str], bytes],
) -> BaseConstraints:
    """`local_constraints_text` is the referenced local file's content (None if there's no
    such reference, or the object doesn't exist)."""
    if local_constraints_text is not None:
        return BaseConstraints(source=local_constraints_uri, text=local_constraints_text)

    constraint_path = find_constraint_path(requirements_text)
    if constraint_path is None:
        entry = FLAGGED_VERSION_TABLE.get(airflow_version)
        if entry is None or not entry.mwaa_forces_upstream_constraints:
            return BaseConstraints(source=None, text=MINIMAL_CONSTRAINTS_HEADER, minimal=True)
        python_version = PYTHON_VERSION_BY_AIRFLOW_VERSION.get(airflow_version)
        if python_version is None:
            return BaseConstraints(source=None, text=None, error=f"no known MWAA Python version for Airflow {airflow_version}")
        url = UPSTREAM_CONSTRAINTS_URL.format(airflow_version=airflow_version, python_version=python_version)
        return replace(_download(url, fetch), mwaa_default=True)
    # an unreadable reference doesn't mean nothing is constrained -- replacing it with the
    # minimal file could drop every other pin it holds
    if constraint_path.startswith(DAGS_MOUNT_PREFIX):
        return BaseConstraints(
            source=local_constraints_uri,
            text=None,
            error=f"--constraint file {constraint_path} doesn't exist; upload it or remove the --constraint line, then re-scan",
        )
    if constraint_path.startswith("http://"):
        return BaseConstraints(
            source=constraint_path,
            text=None,
            error=f"--constraint URL {constraint_path} isn't HTTPS, so it can't be trusted as a base; point it at an https:// URL and re-scan",
        )
    if not constraint_path.startswith("https://"):
        return BaseConstraints(
            source=constraint_path,
            text=None,
            error=(
                f"--constraint file {constraint_path} isn't under {DAGS_MOUNT_PREFIX} or an https:// URL, so it can't be "
                "read as a base; move it under the DAGs folder (or host it over https) and re-scan"
            ),
        )

    apache_versions = parse_apache_constraints_url(constraint_path)
    python_version = PYTHON_VERSION_BY_AIRFLOW_VERSION.get(airflow_version, "unknown")
    if apache_versions and apache_versions != (airflow_version, python_version):
        url_airflow, url_python = apache_versions
        return BaseConstraints(
            source=constraint_path,
            text=None,
            error=(
                f"--constraint URL is for Airflow {url_airflow} / Python {url_python} but this environment runs "
                f"Airflow {airflow_version} (Python {python_version}); fix the --constraint line and re-scan"
            ),
        )
    return _download(constraint_path, fetch)


def _download(url: str, fetch: Callable[[str], bytes]) -> BaseConstraints:
    try:
        return BaseConstraints(source=url, text=fetch(url).decode("utf-8"))
    except (FetchError, UnicodeDecodeError) as exc:
        return BaseConstraints(source=url, text=None, error=f"{exc}; re-run scan once it's reachable")
