# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Per-scope permission preflight.

Queries the ARM `Microsoft.Authorization/permissions` endpoint at each scope
the migration will write to. The response lists every permission entry the
current principal has at that scope (aggregated across roles, including
inherited assignments from management groups). For each required action we
verify at least one entry grants it (and no entry's notActions excludes it
within that same entry).

Run AFTER Phase 1 (build_context) because the monitored subscriptions are
read from the resources-task function app's env vars. Run BEFORE Phase 2 so
permission gaps surface before any resources are created.
"""

import re
from dataclasses import dataclass
from json import JSONDecodeError, loads

from az_shared.errors import AccessError, FatalError
from az_shared.execute_cmd import execute
from az_shared.logs import log

from .constants import MONITORED_SUBSCRIPTIONS_KEY
from .discovery import AzCmd
from .phases.setup import ControlPlaneContext

PERMISSIONS_API_VERSION = "2018-07-01"

# Required actions at the control-plane resource group scope. Covers
# functionapp / serverfarm operations in Phase 4 stop/start + Phase 5 delete,
# container-app job CRUD + start/stop in Phases 2-4, file-share delete in
# Phase 5, and role-assignment management for the deployer in Phase 3 + 5.
CONTROL_PLANE_RG_REQUIRED_ACTIONS: frozenset[str] = frozenset(
    {
        "Microsoft.Web/sites/read",
        "Microsoft.Web/sites/delete",
        "Microsoft.Web/sites/stop/Action",
        "Microsoft.Web/sites/start/Action",
        "Microsoft.Web/sites/config/list/Action",
        "Microsoft.Web/sites/config/Read",
        "Microsoft.Web/serverfarms/read",
        "Microsoft.Web/serverfarms/delete",
        "Microsoft.App/jobs/read",
        "Microsoft.App/jobs/write",
        "Microsoft.App/jobs/delete",
        "Microsoft.App/jobs/start/action",
        "Microsoft.App/jobs/stop/action",
        "Microsoft.App/jobs/executions/read",
        "Microsoft.App/managedEnvironments/read",
        "Microsoft.Storage/storageAccounts/fileServices/shares/delete",
        "Microsoft.Authorization/roleAssignments/read",
        "Microsoft.Authorization/roleAssignments/write",
        "Microsoft.Authorization/roleAssignments/delete",
    }
)

# Required actions on each monitored subscription and on each monitored-sub
# forwarder RG. We only manage role assignments at these scopes in Phase 3.
MONITORED_SCOPE_REQUIRED_ACTIONS: frozenset[str] = frozenset(
    {
        "Microsoft.Authorization/roleAssignments/read",
        "Microsoft.Authorization/roleAssignments/write",
        "Microsoft.Authorization/roleAssignments/delete",
    }
)


@dataclass(frozen=True)
class ScopeCheck:
    """One scope + the set of actions the user must be able to perform there."""

    label: str
    scope: str
    required_actions: frozenset[str]


def _pattern_matches(action: str, pattern: str) -> bool:
    """Case-insensitive wildcard match. Azure uses `*` as the only wildcard."""
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return bool(re.match(regex, action, re.IGNORECASE))


def _action_granted_by_entry(entry: dict, action: str) -> bool:
    """A single permission entry grants `action` when one of its `actions`
    patterns matches AND none of its `notActions` patterns match."""
    actions = entry.get("actions", []) or []
    not_actions = entry.get("notActions", []) or []
    if not any(_pattern_matches(action, p) for p in actions):
        return False
    if any(_pattern_matches(action, p) for p in not_actions):
        return False
    return True


def _action_granted(permission_entries: list[dict], action: str) -> bool:
    return any(_action_granted_by_entry(e, action) for e in permission_entries)


def fetch_permissions(scope: str) -> list[dict]:
    """Call the ARM permissions endpoint for the current principal at `scope`.

    Returns the raw `value` array (each element is one permission entry as
    documented at https://learn.microsoft.com/en-us/rest/api/authorization/permissions/list-for-resource-group).
    """
    url = f"https://management.azure.com{scope}/providers/Microsoft.Authorization/permissions?api-version={PERMISSIONS_API_VERSION}"
    raw = execute(AzCmd("rest", "").param("--method", "GET").param("--url", url))
    try:
        return loads(raw).get("value", [])
    except JSONDecodeError as e:
        raise FatalError(f"Could not parse permissions response for scope {scope}: {e}") from e


def find_missing_actions(scope: str, required: frozenset[str]) -> set[str]:
    """Return the subset of `required` not granted to the current principal at `scope`."""
    entries = fetch_permissions(scope)
    return {action for action in required if not _action_granted(entries, action)}


def _build_scope_checks(ctx: ControlPlaneContext) -> list[ScopeCheck]:
    cp = ctx.control_plane
    control_plane_rg_scope = f"/subscriptions/{cp.sub_id}/resourceGroups/{cp.resource_group}"

    checks: list[ScopeCheck] = [
        ScopeCheck(
            label=f"control plane resource group '{cp.resource_group}'",
            scope=control_plane_rg_scope,
            required_actions=CONTROL_PLANE_RG_REQUIRED_ACTIONS,
        )
    ]

    raw_monitored = ctx.resources_task_env.get(MONITORED_SUBSCRIPTIONS_KEY, "")
    if not raw_monitored:
        raise FatalError(
            f"resources-task for control plane '{cp.control_plane_id}' is missing "
            f"{MONITORED_SUBSCRIPTIONS_KEY}; cannot preflight monitored-subscription permissions."
        )
    try:
        monitored_subs = loads(raw_monitored)
    except JSONDecodeError as e:
        raise FatalError(f"Invalid JSON in {MONITORED_SUBSCRIPTIONS_KEY}: {raw_monitored}") from e
    if not isinstance(monitored_subs, list):
        raise FatalError(f"{MONITORED_SUBSCRIPTIONS_KEY} is not a list: {raw_monitored}")

    for sub_id in monitored_subs:
        sub_scope = f"/subscriptions/{sub_id}"
        rg_scope = f"{sub_scope}/resourceGroups/{cp.resource_group}"
        checks.append(
            ScopeCheck(
                label=f"monitored subscription '{sub_id}'",
                scope=sub_scope,
                required_actions=MONITORED_SCOPE_REQUIRED_ACTIONS,
            )
        )
        checks.append(
            ScopeCheck(
                label=f"forwarder resource group in subscription '{sub_id}'",
                scope=rg_scope,
                required_actions=MONITORED_SCOPE_REQUIRED_ACTIONS,
            )
        )
    return checks


def assert_permissions(ctx: ControlPlaneContext) -> None:
    """Fail-fast preflight: walks every scope the migration will mutate and
    raises AccessError listing every missing action if anything is short."""
    log.info("Running permission preflight...")
    checks = _build_scope_checks(ctx)
    failures: list[str] = []
    for check in checks:
        try:
            missing = find_missing_actions(check.scope, check.required_actions)
        except Exception as e:
            failures.append(
                f"{check.label} ({check.scope}): could not fetch permissions ({e}). "
                "This usually means you lack read access to the scope."
            )
            continue
        if missing:
            failures.append(
                f"{check.label} ({check.scope}): missing actions {sorted(missing)}"
            )

    if failures:
        message = "Preflight permission check failed:\n  - " + "\n  - ".join(failures)
        raise AccessError(message)

    log.info(f"Permission preflight passed for {len(checks)} scope(s)")
