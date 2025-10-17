#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

check_3_9 = {} | {}  # This script must be run with python >= 3.9

# ruff: noqa: E402
from abc import ABC, abstractmethod
from collections.abc import Container, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache, reduce
from http.client import HTTPResponse, HTTPSConnection
import json
from operator import add
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Generator, Literal, Optional, TypeVar, TypedDict, Union

from azure_logging_install.configuration import Configuration
from azure_logging_install.existing_lfo import LfoMetadata, check_existing_lfo
from azure_logging_install.main import install_log_forwarder

# General util

T = TypeVar("T")


class AlgebraicContainer(Container[T]):
    """A container that supports operations of addition and subtraction."""

    def __add__(self, other: Container[T]) -> Container[T]:
        return UnionContainer(self, other)

    def __sub__(self, other: Container[T]) -> Container[T]:
        return DifferenceContainer(self, other)


@dataclass
class UnionContainer(AlgebraicContainer[T]):
    """A container comprised of the union of two containers."""

    c1: Container[T]
    c2: Container[T]

    def __contains__(self, item: T) -> bool:
        return item in self.c1 or item in self.c2


@dataclass
class DifferenceContainer(AlgebraicContainer[T]):
    """A container comprised of the difference of two containers."""

    c1: Container[T]
    c2: Container[T]

    def __contains__(self, item: T) -> bool:
        return item in self.c1 and item not in self.c2


@lru_cache(maxsize=256)
def compile_wildcard(pattern: str) -> re.Pattern:
    """Convert a wildcard expression into a regular expression."""
    return re.compile("^{}$".format(re.escape(pattern).replace(r"\*", ".*")))


JsonAtom = Union[str, int, bool, None]
JsonDict = dict[str, "Json"]
JsonList = list["Json"]
Json = Union[JsonDict, JsonList, JsonAtom]


# Azure util


Action = str


class Permission(TypedDict, total=False):
    """An Azure permission.

    See https://learn.microsoft.com/en-us/rest/api/authorization/permissions/list-for-resource-group#permission."""

    actions: list[Action]
    notActions: list[Action]
    dataActions: list[Action]
    notDataActions: list[Action]


def get_permissions(
    connection: HTTPSConnection, auth_token: str, scope: str
) -> list[Permission]:
    """Fetch the permissions granted over a given scope."""
    connection.request(
        "GET",
        f"{scope}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
    )
    return json.loads(connection.getresponse().read().decode("utf-8"))["value"]


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


@dataclass
class Actions(AlgebraicContainer[Action]):
    """A container of actions that supports operations of addition and subtraction."""

    data: Iterable[Action]

    def __contains__(self, action: Action) -> bool:
        return any(is_action_lte(action, a) for a in self.data)


@dataclass
class FlatPermission:
    """A consolidated permission used to determine whether actions are supported.

    See https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/control-plane-and-data-plane.
    """

    actions: Container[Action]
    data_actions: Container[Action]


def flatten_permissions(permissions: Iterable[Permission]) -> FlatPermission:
    """Create a single permission used to determine whether actions are supported by any of the given permissions."""
    return FlatPermission(
        reduce(
            add,
            [
                Actions(p.get("actions", [])) - Actions(p.get("notActions", []))
                for p in permissions
            ],
            Actions([]),
        ),
        reduce(
            add,
            [
                Actions(p.get("dataActions", [])) - Actions(p.get("notDataActions", []))
                for p in permissions
            ],
            Actions([]),
        ),
    )


def get_flat_permission(auth_token: str, scope: str) -> FlatPermission:
    """Fetch the consolidated permission granted over a given scope."""
    connection = HTTPSConnection("management.azure.com")
    result = flatten_permissions(get_permissions(connection, auth_token, scope))
    connection.close()
    return result


ScopeType = Literal["subscription", "management_group"]


@dataclass
class Scope(ABC):
    """An Azure scope."""

    id: str
    name: str

    @property
    @abstractmethod
    def scope_type(self) -> ScopeType:
        pass

    @property
    @abstractmethod
    def scope(self) -> str:
        pass

    def __hash__(self) -> int:
        return hash(self.id)


class Subscription(Scope):
    """An Azure subscription."""

    @property
    def scope_type(self) -> ScopeType:
        return "subscription"

    @property
    def scope(self) -> str:
        return f"/subscriptions/{self.id}"


@dataclass
class SubscriptionList:
    subscriptions: list[Subscription]


@dataclass
class ManagementGroup(Scope):
    """An Azure management group."""

    subscriptions: SubscriptionList

    @property
    def scope_type(self) -> ScopeType:
        return "management_group"

    @property
    def scope(self) -> str:
        return self.id


@dataclass
class ManagementGroupListResult:
    id: str
    name: str
    az_name: str


@dataclass
class AppRegistration:
    """An Azure app registration."""

    tenant_id: str
    client_id: str
    client_secret: str


@dataclass
class UserSelections:
    """The selections the user has made in the quickstart onboarding UI"""

    scopes: Sequence[Scope]
    app_registration_config: dict
    log_forwarding_config: Optional[dict] = None


class LogForwarderPayload(TypedDict):
    """Log Forwarder format expected by quickstart UI"""

    resourceGroupName: str
    controlPlaneSubscriptionId: str
    controlPlaneSubscriptionName: str
    controlPlaneRegion: str
    tagFilters: Optional[str]
    piiFilters: Optional[str]


def az(cmd: str) -> str:
    """Run Azure CLI command and produce its output. Raise an exception if it fails."""
    try:
        result = subprocess.run(
            f"az {cmd}", shell=True, check=True, text=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Could not execute az command: {str(e.stderr)}")
    else:
        return result.stdout


def az_json(cmd: str) -> Any:
    """Run Azure CLI command and produce its JSON output. Raise an exception if it fails."""
    az_response = az(cmd)
    if not az_response:
        return None
    return json.loads(az_response)


# Datadog utils


def dd_request(
    connection: HTTPSConnection, method: str, endpoint: str, body: Optional[str] = None
) -> HTTPResponse:
    """Submit a request to Datadog."""
    connection.request(
        method,
        endpoint,
        body=body,
        headers={
            "Content-Type": "application/json",
            "DD-API-KEY": os.environ["DD_API_KEY"],
            "DD-APPLICATION-KEY": os.environ["DD_APP_KEY"],
        },
    )
    return connection.getresponse()


def dd_get(connection: HTTPSConnection, endpoint: str) -> HTTPResponse:
    """Submit a GET request to Datadog."""
    return dd_request(connection, "GET", endpoint)


def dd_post(connection: HTTPSConnection, endpoint: str, body: Json) -> HTTPResponse:
    """Submit a POST request to Datadog."""
    return dd_request(connection, "POST", endpoint, body=json.dumps(body))


class Status(Enum):
    STARTED = "STARTED"
    OK = "OK"
    ERROR = "ERROR"


def loading_spinner(message: str, done: threading.Event):
    spinner_chars = ["|", "/", "-", "\\"]
    spinner_char = 0
    while not done.is_set():
        print(f"\r{message}: {spinner_chars[spinner_char]}", end="")
        spinner_char = (spinner_char + 1) % 4
        time.sleep(0.2)


@dataclass
class StatusReporter:
    connection: HTTPSConnection
    workflow_id: str

    def report(
        self,
        step_id: str,
        status: Status,
        message: str,
        metadata: Optional[Json] = None,
    ) -> None:
        """Report the status of a step in a workflow to Datadog."""
        attributes: dict[str, Json] = {
            "message": message,
            "status": status.value,
            "step_id": step_id,
        }
        if metadata:
            attributes["metadata"] = metadata
        dd_post(
            self.connection,
            "/api/unstable/integration/azure/setup/status",
            {
                "data": {
                    "id": self.workflow_id,
                    "type": "add_azure_app_registration",
                    "attributes": attributes,
                },
            },
        ).read()

    @contextmanager
    def report_step(
        self,
        step_id: str,
        loading_message: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """Report the start and outcome of a step in a workflow to Datadog."""
        self.report(step_id, Status.STARTED, f"{step_id}: {Status.STARTED}")
        step_complete: Optional[threading.Event] = None
        loading_message_thread: Optional[threading.Thread] = None
        try:
            if loading_message:
                step_complete = threading.Event()
                loading_message_thread = threading.Thread(
                    target=loading_spinner, args=(loading_message, step_complete)
                )
                loading_message_thread.daemon = True
                loading_message_thread.start()
            step_metadata = {}
            yield step_metadata
        except Exception:
            if step_complete:
                step_complete.set()
            if loading_message_thread:
                loading_message_thread.join()
            self.report(
                step_id,
                Status.ERROR,
                f"{step_id}: {Status.ERROR}: {traceback.format_exc()}",
            )
            raise
        else:
            if step_complete:
                step_complete.set()
            if loading_message_thread:
                loading_message_thread.join()
                # leave line blank and cursor at the beginning
                print(f"\r{' ' * 60}", end="")
                print("\r", end="")
            self.report(
                step_id, Status.OK, f"{step_id}: {Status.OK}", step_metadata or None
            )


@contextmanager
def open_datadog_connection():
    datadog_site = os.environ["DD_SITE"]
    datadog_connection = HTTPSConnection(f"api.{datadog_site}")
    try:
        yield datadog_connection
    finally:
        datadog_connection.close()


# Main


def ensure_login() -> None:
    """Ensure that the user is logged into the Azure CLI. If not, raise an exception."""
    if not az("account show"):
        raise RuntimeError("Not logged in to Azure CLI")


MAX_WORKERS = 50  # This was arbitrary. Feel free to change it.
ASSIGN_ROLES_ACTION = "Microsoft.Authorization/roleAssignments/write"


def filter_scopes_by_permission(scopes: Sequence[Scope]) -> list[Scope]:
    """Filter scopes based on whether the user can assign roles to them.

    Return a list of bools representing whether the scope at each corresponding index should be included."""
    access_token = az_json("account get-access-token")["accessToken"]
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures: list[Future[FlatPermission]] = [
            executor.submit(get_flat_permission, access_token, scope.scope)
            for scope in scopes
        ]
    return [
        scope
        for i, scope in enumerate(scopes)
        if not futures[i].exception()
        and ASSIGN_ROLES_ACTION in futures[i].result().actions
    ]


def get_subscription_scopes():
    return [
        Subscription(**s)
        for s in az_json('account list --query "[].{id:id, name:name}" -o json')
    ]


def get_management_group_from_list_result(
    list_result: ManagementGroupListResult,
) -> ManagementGroup:
    subscriptions_az_response = az_json(
        f'account management-group show --name "{list_result.az_name}" -e -r --query "children[].{{id:id, name:name}}" -o json'
    )
    if subscriptions_az_response:
        subscriptions = [
            Subscription(**s)
            for s in subscriptions_az_response
            if s["id"].startswith("/subscriptions/")
        ]
    else:
        subscriptions = []
    return ManagementGroup(
        id=list_result.id,
        name=list_result.name,
        subscriptions=SubscriptionList(subscriptions),
    )


def get_management_group_scopes() -> list[ManagementGroup]:
    try:
        mgroup_list_results = [
            ManagementGroupListResult(**lr)
            for lr in az_json(
                'account management-group list --query "[].{id:id, az_name:name, name:displayName}" -o json'
            )
        ]
    except RuntimeError:
        # Expected, this means the user doesn't have permissions for any management groups but not necessarily blocking
        return []

    # enrich each result with all of its children subscriptions (at any depth)
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        management_groups = executor.map(
            get_management_group_from_list_result,
            mgroup_list_results,
        )
    return list(management_groups)


def report_available_scopes(
    connection: HTTPSConnection, workflow_id: str
) -> tuple[list[Scope], list[Scope]]:
    """Send Datadog the subscriptions and management groups that the user has permission to grant access to."""
    subscriptions = filter_scopes_by_permission(get_subscription_scopes())
    management_groups = filter_scopes_by_permission(get_management_group_scopes())
    response = dd_post(
        connection,
        "/api/unstable/integration/azure/setup/scopes",
        {
            "data": {
                "id": workflow_id,
                "type": "add_azure_app_registration",
                "attributes": {
                    "subscriptions": {
                        "subscriptions": [asdict(s) for s in subscriptions]
                    },
                    "management_groups": {
                        "management_groups": [asdict(m) for m in management_groups]
                    },
                },
            }
        },
    )
    data = response.read().decode("utf-8")
    if response.status >= 400:
        raise RuntimeError(f"Error submitting available scopes to Datadog: {data}")
    return (subscriptions, management_groups)


def build_log_forwarder_payload(metadata: LfoMetadata) -> LogForwarderPayload:
    return LogForwarderPayload(
        resourceGroupName=metadata.control_plane.resource_group,
        controlPlaneSubscriptionId=metadata.control_plane.sub_id,
        controlPlaneSubscriptionName=metadata.control_plane.sub_name,
        controlPlaneRegion=metadata.control_plane.region,
        tagFilters=metadata.tag_filter,
        piiFilters=metadata.pii_rules,
    )


def report_existing_log_forwarders(
    subscriptions: list[Scope], step_metadata: dict
) -> bool:
    """Send Datadog any existing Log Forwarders in the tenant and return whether we found exactly 1 Forwarder, in which case we will potentially update it."""
    scope_id_to_name = {s.id: s.name for s in subscriptions}
    forwarders = check_existing_lfo(set(scope_id_to_name.keys()), scope_id_to_name)
    step_metadata["log_forwarders"] = [
        build_log_forwarder_payload(forwarder) for forwarder in forwarders.values()
    ]
    return len(forwarders) == 1


def receive_user_selections(
    connection: HTTPSConnection, workflow_id: str
) -> UserSelections:
    """Poll and wait for the user to submit their desired scopes and configuration options."""
    while True:
        response = dd_get(
            connection,
            f"/api/unstable/integration/azure/setup/selections/{workflow_id}",
        )
        data = response.read().decode("utf-8")
        if response.status == 404 or not data:
            time.sleep(1)
            continue
        elif response.status >= 400:
            raise RuntimeError(f"Error retrieving user selections from Datadog: {data}")
        json_response = json.loads(data)
        attributes = json_response["data"]["attributes"]
        return UserSelections(
            tuple(
                [
                    Subscription(**s)
                    for s in attributes["subscriptions"]["subscriptions"]
                ]
                + [
                    ManagementGroup(**mg)
                    for mg in attributes["management_groups"]["management_groups"]
                ]
            ),
            json.loads(attributes["config_options"]),
            json.loads(attributes["log_forwarding_options"])
            if "log_forwarding_options" in attributes
            and attributes["log_forwarding_options"]
            else None,
        )


def flatten_scopes(scopes: Sequence[Scope]) -> set[Subscription]:
    """Convert a list of scopes into a set of subscriptions, with management groups represented as their constituent subscriptions"""
    return set(
        [s for s in scopes if isinstance(s, Subscription)]
        + [
            s
            for subs in [
                m.subscriptions.subscriptions
                for m in scopes
                if isinstance(m, ManagementGroup)
            ]
            for s in subs
        ]
    )


DATADOG_ROLE = "Monitoring Reader"


def create_app_registration_with_permissions(
    scopes: Sequence[Scope],
) -> AppRegistration:
    """Create an app registration with the necessary permissions for Datadog to function over the given scopes."""
    result = az_json(
        f'ad sp create-for-rbac --name "datadog-azure-integration-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}" --role "{DATADOG_ROLE}" --scopes {" ".join([s.scope for s in scopes])}'
    )
    return AppRegistration(result["tenant"], result["appId"], result["password"])


MS_GRAPH_API = "00000003-0000-0000-c000-000000000000"


def add_ms_graph_app_role_assignments(
    app_registration: AppRegistration, roles: list[str]
) -> None:
    """Assign an app registration the necessary app roles for Datadog to function.

    See https://learn.microsoft.com/en-us/graph/permissions-reference for more information."""
    az(
        f'ad app permission add --id "{app_registration.client_id}" --api {MS_GRAPH_API} --api-permissions {" ".join([f"{role}=Role" for role in roles])}'
    )
    # TODO:
    # RuntimeError: Could not execute az command: WARNING: A Cloud Shell credential problem occurred. When you report the issue with the error below, please mention the hostname 'SandboxHost-638863179315458251'
    # ERROR: Audience 74658136-14ec-4630-ad9b-26e160ff0fc6 is not a supported MSI token audience.
    # Interactive authentication is needed. Please run:
    # az login --scope 74658136-14ec-4630-ad9b-26e160ff0fc6/.default
    az(f'ad app permission admin-consent --id "{app_registration.client_id}"')


def submit_integration_config(
    connection: HTTPSConnection, app_registration: AppRegistration, config: dict
) -> None:
    """Submit a new configuration to Datadog."""
    response = dd_post(
        connection,
        "/api/v1/integration/azure",
        {
            **config,
            "client_id": app_registration.client_id,
            "client_secret": app_registration.client_secret,
            "tenant_name": app_registration.tenant_id,
            "source": "quickstart",
            "validate": False,
        },
    )
    data = response.read().decode("utf-8")
    if response.status >= 400:
        raise RuntimeError(f"Error creating Azure Integration in Datadog: {data}")


def submit_config_identifier(
    connection: HTTPSConnection, workflow_id: str, app_registration: AppRegistration
) -> None:
    """Submit an identifier to Datadog for the new configuration so that it can be displayed to the user."""
    response = dd_post(
        connection,
        "/api/unstable/integration/azure/setup/serviceprincipal",
        {
            "data": {
                "id": workflow_id,
                "type": "add_azure_app_registration",
                "attributes": {
                    "client_id": app_registration.client_id,
                    "tenant_id": app_registration.tenant_id,
                },
            }
        },
    )
    data = response.read().decode("utf-8")
    if response.status >= 400:
        raise RuntimeError(
            f"Error submitting configuration identifier to Datadog: {data}"
        )


def upsert_log_forwarder(config: dict, subscriptions: set[Subscription]):
    log_forwarder_config = Configuration(
        control_plane_region=config["controlPlaneRegion"],
        control_plane_sub_id=config["controlPlaneSubscriptionId"],
        control_plane_rg=config["resourceGroupName"],
        monitored_subs=",".join([s.name for s in subscriptions]),
        datadog_api_key=os.environ["DD_API_KEY"],
    )
    if "tagFilters" in config:
        log_forwarder_config.resource_tag_filters = config["tagFilters"]
    if "piiFilters" in config:
        log_forwarder_config.pii_scrubber_rules = config["piiFilters"]

    install_log_forwarder(log_forwarder_config)


def assign_permissions(client_id: str, scopes: Sequence[Scope]) -> None:
    """Assign an app registration the necessary permissions for Datadog to function over the given scopes."""
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        for scope in scopes:
            executor.submit(
                az,
                f'role assignment create --assignee "{client_id}" --role "{DATADOG_ROLE}" --scope "{scope.scope}"',
            )


REQUIRED_ENVIRONMENT_VARS = {
    "DD_API_KEY",
    "DD_APP_KEY",
    "DD_SITE",
    "WORKFLOW_ID",
}


def time_out(datadog_connection: HTTPSConnection, status: StatusReporter):
    status.report("connection", Status.ERROR, "session expired")
    datadog_connection.close()
    print(
        "\nSession expired. If you still wish to create a new Datadog configuration, please reload the onboarding page in Datadog and reconnect using the provided command."
    )
    os._exit(1)


def main():
    if missing_environment_vars := REQUIRED_ENVIRONMENT_VARS - os.environ.keys():
        print(
            f"Missing required environment variables: {', '.join(missing_environment_vars)}"
        )
        sys.exit(1)

    workflow_id = os.environ["WORKFLOW_ID"]

    with open_datadog_connection() as datadog_connection:
        status = StatusReporter(datadog_connection, workflow_id)

        # give up after 30 minutes
        timer = threading.Timer(30 * 60, time_out, [datadog_connection, status])
        timer.daemon = True
        timer.start()

        try:
            with status.report_step("login"):
                ensure_login()
        except Exception as e:
            if "az: command not found" in str(e):
                print("You must install and log in to Azure CLI to run this script.")
            else:
                print(
                    "You must be logged in to Azure CLI to run this script. Run `az login` and try again."
                )
            sys.exit(1)
        else:
            print(
                "Connected! Leave this window open and go back to the Datadog UI to continue."
            )

        with status.report_step("scopes", "Collecting scopes"):
            subscriptions, _ = report_available_scopes(datadog_connection, workflow_id)
        with status.report_step(
            "log_forwarders", "Collecting existing Log Forwarders"
        ) as step_metadata:
            exactly_one_log_forwarder = report_existing_log_forwarders(
                subscriptions, step_metadata
            )
        with status.report_step(
            "selections", "Waiting for user selections in the Datadog UI"
        ):
            selections = receive_user_selections(datadog_connection, workflow_id)
        with status.report_step(
            "app_registration", "Creating app registration in Azure"
        ):
            app_registration = create_app_registration_with_permissions(
                selections.scopes
            )
        with status.report_step(
            "integration_config", "Submitting new configuration to Datadog"
        ):
            submit_integration_config(
                datadog_connection, app_registration, selections.app_registration_config
            )
        with status.report_step(
            "config_identifier", "Submitting new configuration identifier to Datadog"
        ):
            submit_config_identifier(datadog_connection, workflow_id, app_registration)
        if selections.log_forwarding_config:
            with status.report_step(
                "upsert_log_forwarder",
                f"{'Updating' if exactly_one_log_forwarder else 'Creating'} Log Forwarder",
            ):
                upsert_log_forwarder(
                    selections.log_forwarding_config, flatten_scopes(selections.scopes)
                )

    print("Script succeeded. You may close this window.")


if __name__ == "__main__":
    main()
