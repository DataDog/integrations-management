# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Chooses which SessionStore scan/apply should use for one run.

The network intake API is the default now that it exists -- a local tmp
file was always a stand-in for it. Two things fall back to the filesystem
store instead:

  * --offline, explicitly. dd_site/dd_api_key aren't needed at all in this
    case, which is why scan_config.py/apply_config.py only require --dd-site
    when --offline isn't set (see their own docstrings).
  * The intake host being unreachable, checked with a short egress probe
    before committing to it -- so a customer whose CloudShell/network
    genuinely can't reach Datadog gets one clear line and a working local
    fallback instead of a request that hangs or a bare traceback.

These two cases aren't equivalent, which is why the result distinguishes
them (see StoreSelection.forced_by_unreachable_network): explicit --offline
is a deliberate choice that a plain `scan` + a later `apply` still fully
supports. An unreachable network wasn't chosen -- and non-interactive scan's
whole design is to hand off to a UI that will never see a locally-saved
session, so continuing non-interactively there would just strand the
customer with a print-out. scan.py forces --interactive in that case, since
it's the only way left to actually review and apply anything.
"""

import urllib.error
import urllib.request
from typing import NamedTuple, Optional

from .network_session_store import NetworkSessionStore
from .session_store import FilesystemSessionStore, SessionStore


class StoreSelection(NamedTuple):
    store: SessionStore
    forced_by_unreachable_network: bool  # True only for the unreachable-network fallback, never for explicit --offline


def _intake_reachable(dd_site: str, timeout: float = 5.0) -> bool:
    try:
        request = urllib.request.Request(f"https://data-obs-intake.{dd_site}/", method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True  # any HTTP response at all means the network path itself works
    except (urllib.error.URLError, OSError):
        return False


def select_session_store(offline: bool, dd_site: Optional[str], dd_api_key: Optional[str]) -> StoreSelection:
    """Pick a SessionStore for this run, printing why if it's not the network one."""
    if offline:
        return StoreSelection(FilesystemSessionStore(), forced_by_unreachable_network=False)

    # Config parsing requires dd_site/dd_api_key whenever offline isn't set --
    # see scan_config.py/apply_config.py -- so reaching here without them is a
    # bug in this codebase, not a customer-reachable state.
    assert dd_site and dd_api_key, "select_session_store needs dd_site/dd_api_key unless offline"

    if not _intake_reachable(dd_site):
        print(f"Could not reach the Datadog intake API at data-obs-intake.{dd_site} -- falling back to local filesystem storage.")
        return StoreSelection(FilesystemSessionStore(), forced_by_unreachable_network=True)

    return StoreSelection(NetworkSessionStore(dd_site=dd_site, dd_api_key=dd_api_key), forced_by_unreachable_network=False)
