# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared Azure RBAC helpers for the agentless setup wizard.

The wizard self-grants two data-plane roles - ``Storage Blob Data
Contributor`` on the Terraform-state Storage Account and ``Key Vault
Secrets Officer`` on the Key Vault. Both grants follow the same shape:

  1. resolve the signed-in user's Entra object ID;
  2. resolve the target resource ID (the only step that differs between
     the two grants);
  3. check whether the role already exists at that scope (idempotency);
  4. create the role assignment if it does not.

Centralising the shared steps keeps the ``--subscription`` threading,
the role-already-exists short-circuit, and the error wrapping in a
single place. Each domain wrapper supplies its own resource resolver
and its own ``*Error`` class so user-facing errors stay specific.
"""

from typing import Callable

from az_shared.execute_cmd import execute
from common.shell import Cmd


def grant_role_to_current_user(
    *,
    role: str,
    resource_id_lookup: Callable[[], str],
    subscription: str,
    error_cls: type[Exception],
    error_message: str,
) -> bool:
    """Idempotently grant ``role`` on a resource to the signed-in user.

    Args:
        role: Azure RBAC role display name (e.g. ``"Storage Blob Data
            Contributor"``).
        resource_id_lookup: Zero-arg callable returning the ARM resource
            ID to scope the role to. Called inside the helper's
            ``try`` block so a lookup failure is wrapped in
            ``error_cls`` alongside the rest of the flow.
        subscription: Scanner subscription. Threaded through every inner
            ``az`` call: the Cloud Shell user's default subscription is
            unreliable (Cloud Shell picks an arbitrary one at startup),
            and the destroy path never calls ``set_subscription``, so
            without this every step would silently target the wrong sub.
        error_cls: Domain-specific exception class to raise on
            unexpected failures (``StorageAccountError`` /
            ``KeyVaultError``); already-typed errors propagate
            untouched.
        error_message: Top-line message for the wrapped error.

    Returns:
        ``True`` if a new role assignment was created (caller should
        wait for RBAC propagation), ``False`` if the role already
        existed at this scope.

    Raises:
        ``error_cls``: on any unexpected failure during signed-in-user
            lookup, resource lookup, role list, or role create.
    """
    try:
        user_object_id = execute(
            Cmd(["az", "ad", "signed-in-user", "show"])
            .param("--query", "id")
            .param("--output", "tsv")
        ).strip()

        resource_id = resource_id_lookup()

        existing = execute(
            Cmd(["az", "role", "assignment", "list"])
            .param("--assignee", user_object_id)
            .param("--role", role)
            .param("--scope", resource_id)
            .param("--subscription", subscription)
            .param("--query", "length(@)")
            .param("--output", "tsv"),
            can_fail=True,
        )
        if existing.strip() not in ("", "0"):
            return False

        execute(
            Cmd(["az", "role", "assignment", "create"])
            .param("--assignee-object-id", user_object_id)
            .param("--assignee-principal-type", "User")
            .param("--role", role)
            .param("--scope", resource_id)
            .param("--subscription", subscription)
        )
        return True
    except error_cls:
        raise
    except Exception as e:
        raise error_cls(error_message, str(e)) from e
