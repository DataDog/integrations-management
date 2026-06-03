# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import argparse
import logging
from logging import basicConfig

from az_shared.errors import InputParamValidationError
from az_shared.logs import log, log_header

from .discovery import discover_control_planes
from .migration import migrate_control_plane
from .phases.setup import build_context
from .preflight import assert_permissions
from .steps import RollbackError


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate LFO control planes from Function Apps to Container App Jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--control-plane-subscription",
        type=str,
        default=None,
        help="Limit migration to a single subscription (default: all subscriptions visible to the current user).",
    )
    parser.add_argument(
        "--control-plane-id",
        type=str,
        default=None,
        help="Limit migration to a single 12-character control plane ID suffix.",
    )
    parser.add_argument(
        "--check-user-permissions",
        action="store_true",
        help="Run only the discovery + permission preflight against every discovered "
        "control plane, then exit. No resources are created, modified, or deleted. "
        "Use this to verify the running identity has all permissions needed before "
        "committing to a migration.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the log level (default: INFO).",
    )
    return parser.parse_args()


def check_permissions_only(control_planes: list) -> int:
    """Run preflight for each control plane and report. Returns process exit code."""
    failures: list[tuple[str, str]] = []
    for cp in control_planes:
        log_header(f"Checking permissions for control plane '{cp.control_plane_id}'")
        try:
            ctx = build_context(cp)
            assert_permissions(ctx)
            log.info(f"Control plane '{cp.control_plane_id}': permission check PASSED")
        except Exception as e:
            log.error(f"Control plane '{cp.control_plane_id}': permission check FAILED")
            log.error(str(e))
            failures.append((cp.control_plane_id, str(e)))

    log_header("Permission check summary")
    log.info(f"Total control planes checked: {len(control_planes)}")
    log.info(f"  Passed: {len(control_planes) - len(failures)}")
    log.info(f"  Failed: {len(failures)}")
    if failures:
        log.error("Failed control planes:")
        for cp_id, err in failures:
            log.error(f"  - {cp_id}: {err}")
        return 1
    return 0


def main() -> None:
    try:
        args = parse_arguments()
    except Exception as e:
        raise InputParamValidationError(f"Failed to parse arguments: {e}") from e

    basicConfig(level=getattr(logging, args.log_level))

    log_header("Discovering LFO control planes")
    control_planes = discover_control_planes(
        subscription_filter=args.control_plane_subscription,
        control_plane_id_filter=args.control_plane_id,
    )
    if not control_planes:
        log.info("No LFO control planes found matching the supplied filters.")
        return

    log.info(f"Found {len(control_planes)} control plane(s):")
    for cp in control_planes:
        log.info(f"  - {cp.control_plane_id} in subscription {cp.sub_id} (resource group {cp.resource_group})")

    if args.check_user_permissions:
        raise SystemExit(check_permissions_only(control_planes))

    overall_manual_actions: list[tuple[str, list[str]]] = []
    overall_failures: list[tuple[str, str]] = []

    for cp in control_planes:
        try:
            manual = migrate_control_plane(cp)
            if manual:
                overall_manual_actions.append((cp.control_plane_id, manual))
        except RollbackError as e:
            log.error(f"Control plane '{cp.control_plane_id}' migration aborted and rolled back: {e}")
            overall_failures.append((cp.control_plane_id, str(e)))
        except Exception as e:
            log.error(f"Unexpected failure on control plane '{cp.control_plane_id}': {e}")
            overall_failures.append((cp.control_plane_id, str(e)))

    log_header("Migration summary")
    log.info(f"Total control planes processed: {len(control_planes)}")
    log.info(f"  Failures (rolled back): {len(overall_failures)}")
    log.info(f"  Completed with manual cleanup outstanding: {len(overall_manual_actions)}")
    log.info(
        f"  Completed cleanly: "
        f"{len(control_planes) - len(overall_failures) - len(overall_manual_actions)}"
    )

    if overall_failures:
        log.error("The following control planes failed migration and were rolled back:")
        for cp_id, err in overall_failures:
            log.error(f"  - {cp_id}: {err}")

    if overall_manual_actions:
        log.warning("Manual cleanup required for these control planes:")
        for cp_id, actions in overall_manual_actions:
            log.warning(f"Control plane '{cp_id}':")
            for action in actions:
                log.warning(f"  - {action}")

    if overall_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
