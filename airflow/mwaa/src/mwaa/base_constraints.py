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

When either of those can't be read, there's no safe file to write, so `text`
is None and plan.py leaves the package changes out entirely (see
check_base_constraints for the issue that records why).

  3. Otherwise (no --constraint line, or one this tool can't read as a base)
     the file written is minimal: MINIMAL_CONSTRAINTS_HEADER plus just the
     OpenLineage pins. Not the full upstream constraints file the upgrade
     guide patches: a customer's own pins routinely postdate an old Airflow
     release's upstream file (boto3, say), and pip then refuses to install
     anything from requirements.txt -- while MWAA still reports the update as
     a success. MWAA installs apache-airflow==<version> as a top-level
     requirement itself, so Airflow stays pinned either way.
"""

import re
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Optional

from .fetch import FetchError
from .pins import find_constraint_path
from .version_table import PYTHON_VERSION_BY_AIRFLOW_VERSION


@dataclass(frozen=True)
class BaseConstraints:
    source: Optional[str]  # an s3:// URI or https URL; None if not even a source could be determined
    text: Optional[str]  # None when it couldn't be read -- see error
    error: Optional[str] = None
    minimal: bool = False  # case 3: no base to patch, just the header the pins get appended to


MINIMAL_CONSTRAINTS_HEADER = (
    "# Pins only the OpenLineage packages Datadog Data Observability needs; every other package resolves as it would without a constraints file.\n"
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
    such reference, or the object doesn't exist -- then the file written is minimal, case 3)."""
    if local_constraints_text is not None:
        return BaseConstraints(source=local_constraints_uri, text=local_constraints_text)

    constraint_path = find_constraint_path(requirements_text)
    if constraint_path and constraint_path.startswith("http://"):
        return BaseConstraints(
            source=constraint_path,
            text=None,
            error=f"--constraint URL {constraint_path} isn't HTTPS, so it can't be trusted as a base; point it at an https:// URL and re-scan",
        )
    if not constraint_path or not constraint_path.startswith("https://"):
        return BaseConstraints(source=None, text=MINIMAL_CONSTRAINTS_HEADER, minimal=True)

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
    try:
        return BaseConstraints(source=constraint_path, text=fetch(constraint_path).decode("utf-8"))
    except (FetchError, UnicodeDecodeError) as exc:
        return BaseConstraints(source=constraint_path, text=None, error=f"{exc}; re-run scan once it's reachable")
