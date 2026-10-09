# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Is OpenLineage *effectively* configured to send to Datadog? Judged statically.

"Configured" means the configuration the provider will actually resolve is
right -- not that startup.sh matches the docs' snippet line for line, and not
that events are flowing (the UI's Run a DAG step checks that). Datadog's docs
recipe (OPENLINEAGE_URL + OPENLINEAGE_API_KEY + AIRFLOW__OPENLINEAGE__NAMESPACE,
plus the two 2.7/2.8 workaround variables) is the canonical case; anything else
that resolves to an HTTP transport to https://data-obs-intake.<site> with an API
key counts too.

Inputs are the environment the provider runs with: AirflowConfigurationOptions'
openlineage.* keys (MWAA exports them as AIRFLOW__OPENLINEAGE__*), overlaid with
what startup.sh exports (shell_env.py). Transport resolution then follows the
provider and openlineage-python source, verified at provider 1.14.0, 2.14.0 and
2.18.0 (plugins/adapter.py get_openlineage_config, conf.py is_disabled) and
openlineage-python 1.24.2 and 1.49.0 (client.py _resolve_transport, config,
_alias_env_vars, _load_config_from_env_variables):

  0. [openlineage] disabled, or OPENLINEAGE_DISABLED -- nothing is sent.
     Provider < 2.6.0 also disables itself when none of transport/config_path/
     OPENLINEAGE_CONFIG/OPENLINEAGE_URL is set, even if OPENLINEAGE__TRANSPORT__*
     env vars are; 2.6.0 added those env vars to the check.
  1. [openlineage] config_conn_id (provider >= 2.18.0) -- an Airflow connection.
  2. [openlineage] config_path -- a YAML file (only when non-empty; the 2.7/2.8
     workaround sets it to "").
  3. [openlineage] transport -- JSON, passed to the client as its config.
  4. openlineage-python then merges, lowest to highest precedence, the
     OPENLINEAGE__* env-style config, the OPENLINEAGE_CONFIG YAML file, and the
     config from 3. -- so that file only matters for what 3. leaves unset. If that config's transport has a type, that's the transport.
     OPENLINEAGE_URL/OPENLINEAGE_API_KEY are always aliased into the env-style
     config as a `default_http` sub-transport first (unless one is already
     defined there), so they also reach a composite transport.
  5. Otherwise OPENLINEAGE_URL (+ OPENLINEAGE_API_KEY) is an HTTP transport.
  6. Otherwise events go to the console.

A config file or connection can't be read statically, so either one winning is
a WARN ("can't verify"), never a guess. When the transport that wins goes
somewhere other than the intake and setting OPENLINEAGE_URL wouldn't change
that, it's a FAIL naming the winning variable -- the plan proposes no transport
change there, since it wouldn't take effect.
"""

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from airflow_shared.reporter import Finding, FindingStatus

from .pins import OPENLINEAGE_PROVIDER, mentions_package, requirement_line_package
from .shell_env import Variables, exported_environment
from .startup_script import DD_API_KEY_PLACEHOLDER, VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND

PROVIDER_ENV_STYLE_TRANSPORT_VERSION = (2, 6, 0)
_TRUE = ("true", "1", "t")
_UNKNOWN = object()  # a value set to something that can't be known statically
_PROVIDER_MENTION = re.compile(r"apache[-_.]airflow[-_.]providers[-_.]openlineage", re.IGNORECASE)


@dataclass(frozen=True)
class OpenLineageState:
    """What the provider would effectively do, as far as it can be told statically."""

    configured: bool
    # setting OPENLINEAGE_URL/OPENLINEAGE_API_KEY would make it resolve there -- the only
    # case the plan proposes changing either one
    transport_fixable: bool
    issues: list[Finding] = field(default_factory=list)
    environment: Variables = field(default_factory=dict)


@dataclass(frozen=True)
class _Resolution:
    """Where the effective transport sends: ok, somewhere else (destinations), or unknowable (reason)."""

    ok: bool
    winner: Optional[str] = None
    destinations: tuple[str, ...] = ()
    unknown: Optional[str] = None
    disables: bool = False


def effective_environment(startup_script_text: Optional[str], configuration_options: dict) -> Variables:
    """AirflowConfigurationOptions' openlineage.* keys as MWAA exports them, overlaid with startup.sh's exports."""
    environment: Variables = {
        f"AIRFLOW__OPENLINEAGE__{key.split('.', 1)[1].upper()}": str(value)
        for key, value in (configuration_options or {}).items()
        if key.startswith("openlineage.")
    }
    environment.update(exported_environment(startup_script_text or ""))
    return environment


def is_intake_url(url: Any, dd_site: str) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() == f"data-obs-intake.{dd_site}"


def _has_api_key(auth: Any) -> bool:
    if isinstance(auth, str):
        try:
            auth = json.loads(auth)
        except json.JSONDecodeError:
            return False
    if not isinstance(auth, dict) or auth.get("type") != "api_key":
        return False
    key = next((auth[k] for k in ("apiKey", "apikey", "api_key") if k in auth), None)
    return key is _UNKNOWN or bool(key)


def _evaluate(transport: dict, dd_site: str, winner: str) -> _Resolution:
    kind = transport.get("type")
    if kind is _UNKNOWN:
        return _Resolution(ok=False, winner=winner, unknown="its transport type")
    if kind in ("http", "async_http"):
        url = transport.get("url")
        if url is _UNKNOWN:
            return _Resolution(ok=False, winner=winner, unknown="the URL it sends to")
        if is_intake_url(url, dd_site) and _has_api_key(transport.get("auth")):
            return _Resolution(ok=True, winner=winner)
        destination = f"{url} without an API key" if is_intake_url(url, dd_site) else str(url)
        return _Resolution(ok=False, winner=winner, destinations=(destination,))
    if kind == "composite":
        transports = transport.get("transports") or {}
        children = list(transports.values()) if isinstance(transports, dict) else list(transports)
        results = [_evaluate(child, dd_site, winner) for child in children if isinstance(child, dict)]
        if any(r.ok for r in results):
            return _Resolution(ok=True, winner=winner)
        unknown = next((r.unknown for r in results if r.unknown), None)
        if unknown:
            return _Resolution(ok=False, winner=winner, unknown=unknown)
        return _Resolution(ok=False, winner=winner, destinations=tuple(d for r in results for d in r.destinations) or ("no HTTP transport",))
    return _Resolution(ok=False, winner=winner, destinations=(f"a {kind} transport",))


def _env_style_config(environment: Variables) -> dict:
    """openlineage-python's _load_config_from_env_variables, after _alias_env_vars."""
    env = dict(environment)
    url = env.get("OPENLINEAGE_URL")
    if "OPENLINEAGE_URL" in env and url != "" and not any(k.startswith("OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP") for k in env):
        api_key = env.get("OPENLINEAGE_API_KEY")
        env["OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__TYPE"] = "http"
        env["OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__URL"] = url
        if "OPENLINEAGE_API_KEY" in env and api_key != "":
            env["OPENLINEAGE__TRANSPORT__TRANSPORTS__DEFAULT_HTTP__AUTH"] = {"type": "api_key", "apiKey": _UNKNOWN if api_key is None else api_key}
        if env.get("OPENLINEAGE__TRANSPORT__TYPE") == "async_http":
            env.setdefault("OPENLINEAGE__TRANSPORT__URL", url)

    config: dict = {}
    for key, value in sorted(((k, v) for k, v in env.items() if k.startswith("OPENLINEAGE__")), reverse=True):
        if value is None:
            value = _UNKNOWN
        elif isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        current = config
        path = [part.lower() for part in key[len("OPENLINEAGE__") :].split("__")]
        for part in path[:-1]:
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[path[-1]] = value
    return config


def _deep_merge(lower: dict, higher: dict) -> dict:
    merged = dict(lower)
    for key, value in higher.items():
        merged[key] = _deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


def is_set(environment: Variables, name: str) -> bool:
    """Set to something non-empty, or to something unknowable."""
    return name in environment and environment[name] != ""


def _resolve(environment: Variables, dd_site: str, provider_version: Optional[tuple]) -> _Resolution:
    for name in ("AIRFLOW__OPENLINEAGE__DISABLED", "OPENLINEAGE_DISABLED"):
        if name in environment and environment[name] is None:
            return _Resolution(ok=False, winner=name, unknown=f"whether {name} disables it")
        if (environment.get(name) or "").strip().lower() in _TRUE:
            return _Resolution(ok=False, winner=name, disables=True)

    for name, what in (
        ("AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID", "the Airflow connection it names"),
        ("AIRFLOW__OPENLINEAGE__CONFIG_PATH", "the config file it points at"),
    ):
        if is_set(environment, name):
            return _Resolution(ok=False, winner=name, unknown=what)

    user_config: dict = {}
    winner = None
    if is_set(environment, "AIRFLOW__OPENLINEAGE__TRANSPORT"):
        raw = environment["AIRFLOW__OPENLINEAGE__TRANSPORT"]
        if raw is None:
            return _Resolution(ok=False, winner="AIRFLOW__OPENLINEAGE__TRANSPORT", unknown="its value")
        try:
            user_config = {"transport": json.loads(raw)}
        except json.JSONDecodeError:
            return _Resolution(ok=False, winner="AIRFLOW__OPENLINEAGE__TRANSPORT", unknown="its value, which isn't valid JSON")
        winner = "AIRFLOW__OPENLINEAGE__TRANSPORT"
    if is_set(environment, "OPENLINEAGE_CONFIG"):
        # the client merges that file *below* the config passed from 3., so it can only fill
        # in what that config leaves out: a decisive Airflow transport still decides
        if user_config:
            decided = _evaluate(user_config["transport"], dd_site, winner)
            transport = user_config["transport"]
            wrong_url = transport.get("type") in ("http", "async_http") and isinstance(transport.get("url"), str) and not is_intake_url(transport["url"], dd_site)
            if decided.ok or wrong_url:
                return decided
        return _Resolution(ok=False, winner="OPENLINEAGE_CONFIG", unknown="the config file it points at")

    env_config = _env_style_config(environment)
    if winner is None and not is_set(environment, "OPENLINEAGE_URL") and any(is_set(environment, k) for k in environment if k.startswith("OPENLINEAGE__TRANSPORT")):
        # provider < 2.6.0 disables itself without transport/config_path/OPENLINEAGE_URL (conf.is_disabled)
        if provider_version is None:
            return _Resolution(
                ok=False,
                winner="OPENLINEAGE__TRANSPORT__*",
                unknown="the provider version: before 2.6.0 it disables itself when only OPENLINEAGE__TRANSPORT__* is set",
            )
        if provider_version < PROVIDER_ENV_STYLE_TRANSPORT_VERSION:
            return _Resolution(ok=False, winner="OPENLINEAGE__TRANSPORT__*", destinations=("nowhere -- the pinned provider is before 2.6.0, which ignores it",))

    transport = _deep_merge(env_config, user_config).get("transport")
    if isinstance(transport, dict) and transport.get("type"):
        return _evaluate(transport, dd_site, winner or "OPENLINEAGE__TRANSPORT__TYPE")
    if is_set(environment, "OPENLINEAGE_URL"):
        url = environment["OPENLINEAGE_URL"]
        api_key = environment.get("OPENLINEAGE_API_KEY")
        auth = {"type": "api_key", "apiKey": _UNKNOWN if api_key is None else api_key} if "OPENLINEAGE_API_KEY" in environment else None
        return _evaluate({"type": "http", "url": _UNKNOWN if url is None else url, "auth": auth}, dd_site, "OPENLINEAGE_URL")
    return _Resolution(ok=False, destinations=("the console -- no transport is configured",))


def _provider_version(requirements_text: str) -> Optional[tuple]:
    for line in requirements_text.splitlines():
        if requirement_line_package(line) != OPENLINEAGE_PROVIDER:
            continue
        pinned = re.search(r"==\s*([0-9][0-9.]*)", line) or re.search(r"-([0-9][0-9.]*)-py3-none-any\.whl", line)
        if pinned:
            return tuple(int(part) for part in pinned.group(1).strip(".").split("."))
    return None


def analyze(airflow_version: str, requirements_text: str, startup_script_text: Optional[str], configuration_options: dict, dd_site: str) -> OpenLineageState:
    environment = effective_environment(startup_script_text, configuration_options)
    provider_version = _provider_version(requirements_text)
    resolution = _resolve(environment, dd_site, provider_version)
    issues: list[Finding] = []

    fixed = dict(environment)
    if not is_intake_url(fixed.get("OPENLINEAGE_URL"), dd_site):
        fixed["OPENLINEAGE_URL"] = f"https://data-obs-intake.{dd_site}"
    if not is_set(fixed, "OPENLINEAGE_API_KEY"):
        fixed["OPENLINEAGE_API_KEY"] = DD_API_KEY_PLACEHOLDER
    fixable = not resolution.ok and resolution.unknown is None and _resolve(fixed, dd_site, provider_version).ok

    if resolution.unknown:
        issues.append(
            Finding(
                "openlineage_transport",
                FindingStatus.WARN,
                f"{resolution.winner} decides where OpenLineage sends, but this can't verify {resolution.unknown}",
                "Not counted as configured, and no OPENLINEAGE_URL/OPENLINEAGE_API_KEY change is proposed. "
                "Run the OpenLineage validation DAG to confirm where events go.",
            )
        )
    elif resolution.disables:
        issues.append(
            Finding(
                "openlineage_transport",
                FindingStatus.FAIL,
                f"{resolution.winner} is set to {environment[resolution.winner]!r}, which disables OpenLineage, so nothing is sent",
                f"Remove {resolution.winner} from the startup script / airflow_configuration_options, then re-scan.",
            )
        )
    elif not resolution.ok and not fixable and resolution.winner:
        issues.append(
            Finding(
                "openlineage_transport",
                FindingStatus.FAIL,
                f"{resolution.winner} is set and takes precedence over OPENLINEAGE_URL; it sends to "
                f"{', '.join(resolution.destinations)}, so an OPENLINEAGE_URL change would not take effect",
                f"Point it at https://data-obs-intake.{dd_site} (with an API key), or remove it, then re-scan.",
            )
        )

    provider_present = mentions_package(requirements_text, OPENLINEAGE_PROVIDER)
    if not provider_present and _PROVIDER_MENTION.search(startup_script_text or ""):
        issues.append(
            Finding(
                "openlineage_provider",
                FindingStatus.WARN,
                f"{OPENLINEAGE_PROVIDER} isn't in requirements.txt; the startup script appears to install it, which can't be verified",
                "Not counted as configured. Add it to requirements.txt so MWAA installs it under its constraints.",
            )
        )

    workaround_ok = airflow_version not in VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND or all(
        name in environment for name in ("AIRFLOW__OPENLINEAGE__CONFIG_PATH", "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS")
    )
    configured = resolution.ok and provider_present and is_set(environment, "AIRFLOW__OPENLINEAGE__NAMESPACE") and workaround_ok
    return OpenLineageState(configured=configured, transport_fixable=fixable, issues=issues, environment=environment)

