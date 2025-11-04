# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Container, Iterable
from dataclasses import dataclass

from azure_integration_quickstart.util import compile_wildcard

Action = str


def is_action_lte(a1: Action, a2: Action) -> bool:
    """Determine whether an action is encompassed by, or "less than or equal to", another action.

    Examples:
    >>> is_action_lte("Microsoft.Compute/virtualMachines/read", "*/read")  # True
    >>> is_action_lte("*/read", "Microsoft.Compute/virtualMachines/read")  # False
    >>> is_action_lte("*/read", "*/read")  # True
    >>> is_action_lte("*/read", "Microsoft.Compute/virtualMachines/*")  # False

    See https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions#actions-format.
    """
    return bool(compile_wildcard(a2.lower()).match(a1.lower()))


def is_action_overlapping(a1: Action, a2: Action) -> bool:
    """Determine whether an action has any overlap with another action."""
    return is_action_lte(a1, a2) or is_action_lte(a2, a1)


@dataclass
class ActionContainer(Container[Action]):
    """A container of actions."""

    actions: Iterable[Action]
    not_actions: Iterable[Action]

    def __contains__(self, action: Action) -> bool:
        return (any(is_action_lte(action, a) for a in self.actions)) and not (
            any(is_action_overlapping(a, action) for a in self.not_actions)
        )
