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

Capabilities that only exist from some release on (config_conn_id, the
async_http transport, the lowercase `apikey` auth spelling, env-style-only
config -- see the version constants below) only count when the installed
version is known to have them: pinned in requirements.txt, else in the
constraints file in effect. When it isn't pinned, that's a can't-verify WARN.

A config file or connection can't be read statically, so either one winning is
a WARN ("can't verify"), never a guess. When the transport that wins goes
somewhere other than the intake and setting OPENLINEAGE_URL wouldn't change
that, it's a FAIL naming the winning variable -- the plan proposes no transport
change there, since it wouldn't take effect. The exception is an
AIRFLOW__OPENLINEAGE__TRANSPORT that startup.sh exports on one line and that's
aimed at a Datadog intake (any site): it's obviously meant for Datadog, so
OpenLineageState.transport_rewrite is the url and API key fields to set in it,
for apply to merge into that line in place (keeping its other fields).
"""

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from airflow_shared.reporter import Finding, FindingStatus

from .pins import OPENLINEAGE_PROVIDER, mentions_package, pinned_versions, requirement_line_package
from .shell_env import Variables, exported_environment
from .startup_script import DD_API_KEY_PLACEHOLDER, VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND

# version boundaries, from the provider/openlineage-python source at each release
PROVIDER_ENV_STYLE_TRANSPORT_VERSION = (2, 6, 0)  # conf.is_disabled counts OPENLINEAGE__TRANSPORT* env vars
PROVIDER_CONFIG_CONN_ID_VERSION = (2, 18, 0)  # adapter.get_openlineage_config reads config_conn_id
CLIENT_ASYNC_HTTP_VERSION = (1, 35, 0)  # transport/__init__.py registers async_http
CLIENT_LOWERCASE_APIKEY_VERSION = (1, 38, 0)  # transport/http.py accepts auth "apikey"
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
    # the fields (JSON) to set in AIRFLOW__OPENLINEAGE__TRANSPORT, when it's aimed at a Datadog
    # intake and startup.sh's one export of it can be rewritten in place -- see _datadog_transport_rewrite
    transport_rewrite: Optional[str] = None
    # the literal Datadog API key the transport in use sends with, if there is one -- kept in
    # memory only so the scan can check it (session.py); never persisted, printed or repr'd
    existing_api_key: Optional[str] = field(default=None, repr=False)
    # where that key is set: "OPENLINEAGE_API_KEY" or "AIRFLOW__OPENLINEAGE__TRANSPORT"
    api_key_source: Optional[str] = None
    # OPENLINEAGE_URL is another Datadog site's intake, so a key set next to it is that site's
    api_key_site_changes: bool = False
    # the key is set by one assignment the plan can replace in place (see _single_standalone_key_export)
    api_key_editable: bool = False
    # the TRANSPORT fields to set if its key has to be replaced (see _datadog_transport_rewrite)
    transport_key_rewrite: Optional[str] = None


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


_ANY_DATADOG_INTAKE = re.compile(r"data-obs-intake\.(?:[a-z0-9-]+\.)*(?:datadoghq\.com|datadoghq\.eu|ddog-gov\.com|datad0g\.com)")
_TRANSPORT_VAR = "AIRFLOW__OPENLINEAGE__TRANSPORT"
# what a Datadog API key looks like, typed into the script as is -- not a $(...), a
# variable or a secret lookup, which can't be checked and are never replaced
_LITERAL_API_KEY = re.compile(r"[0-9a-fA-F]{32}")
# `export OPENLINEAGE_API_KEY=<literal key>`, optionally quoted, optionally followed by a comment
_STANDALONE_KEY_EXPORT = re.compile(r"""\s*export\s+OPENLINEAGE_API_KEY=(?:'[0-9a-fA-F]{32}'|"[0-9a-fA-F]{32}"|[0-9a-fA-F]{32})(?:\s+#.*)?\s*""")


# the value of an OPENLINEAGE_API_KEY assignment is a literal key token, not an expansion
_LITERAL_KEY_ASSIGNMENT = re.compile(r"""OPENLINEAGE_API_KEY=(?:'[0-9a-fA-F]{32}'|"[0-9a-fA-F]{32}"|[0-9a-fA-F]{32})(?=$|[\s;&|#])""")


def _effective_key_assignment_is_literal(startup_script_text: str) -> bool:
    """The last OPENLINEAGE_API_KEY assignment -- the one in effect -- types the key in as is.

    A key that only resolves through a variable is never checked: what's
    eligible is a key written into the script, nothing derived.
    """
    lines = [line for line in startup_script_text.splitlines() if "OPENLINEAGE_API_KEY=" in line]
    return bool(lines) and bool(_LITERAL_KEY_ASSIGNMENT.match("OPENLINEAGE_API_KEY=" + lines[-1].rsplit("OPENLINEAGE_API_KEY=", 1)[1]))


def _single_standalone_key_export(startup_script_text: str) -> bool:
    """OPENLINEAGE_API_KEY is assigned exactly once, by a standalone literal export patch_env_vars can replace.

    A second assignment would win over the one replaced, and anything sharing
    its line would be lost.
    """
    lines = [line for line in startup_script_text.splitlines() if "OPENLINEAGE_API_KEY=" in line]
    return startup_script_text.count("OPENLINEAGE_API_KEY=") == 1 and bool(_STANDALONE_KEY_EXPORT.fullmatch(lines[0]))


def is_any_datadog_intake_url(url: Any) -> bool:
    """A data-obs-intake URL for any Datadog site, not just the one being onboarded."""
    if not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https") and bool(_ANY_DATADOG_INTAKE.fullmatch((parsed.hostname or "").lower()))


def _api_key(auth: Any, client_version: Optional[tuple]) -> Optional[bool]:
    """Whether an http transport's auth carries a non-empty API key openlineage-python will use; None if that can't be told.

    The two parser generations pick differently (transport/http.py
    ApiKeyTokenProvider): before 1.38.0, `api_key` whenever it's present, else
    `apiKey`; from 1.38.0, the first non-empty of `apiKey`, `apikey`, `api_key`.
    With the client version unknown, only an answer both agree on counts.
    """
    if isinstance(auth, str):
        try:
            auth = json.loads(auth)
        except json.JSONDecodeError:
            return False
    if not isinstance(auth, dict) or auth.get("type") != "api_key":
        return False
    before = bool(auth["api_key"] if "api_key" in auth else auth.get("apiKey"))
    from_1_38 = bool(auth.get("apiKey") or auth.get("apikey") or auth.get("api_key"))
    if client_version is None:
        return before if before == from_1_38 else None
    return from_1_38 if client_version >= CLIENT_LOWERCASE_APIKEY_VERSION else before


def _evaluate(transport: dict, dd_site: str, winner: str, client_version: Optional[tuple]) -> _Resolution:
    kind = transport.get("type")
    if kind is _UNKNOWN:
        return _Resolution(ok=False, winner=winner, unknown="its transport type")
    if kind == "async_http" and (client_version is None or client_version < CLIENT_ASYNC_HTTP_VERSION):
        if client_version is None:
            return _Resolution(ok=False, winner=winner, unknown="whether the installed openlineage-python has the async_http transport (1.35.0+)")
        return _Resolution(ok=False, winner=winner, destinations=("an async_http transport, which the pinned openlineage-python doesn't have",))
    if kind in ("http", "async_http"):
        url = transport.get("url")
        if url is _UNKNOWN:
            return _Resolution(ok=False, winner=winner, unknown="the URL it sends to")
        api_key = _api_key(transport.get("auth"), client_version)
        if is_intake_url(url, dd_site) and api_key is None:
            return _Resolution(
                ok=False, winner=winner, unknown="which API key alias the installed openlineage-python picks (it changed in 1.38.0)"
            )
        if is_intake_url(url, dd_site) and api_key:
            return _Resolution(ok=True, winner=winner)
        destination = f"{url} without an API key" if is_intake_url(url, dd_site) else str(url)
        return _Resolution(ok=False, winner=winner, destinations=(destination,))
    if kind == "composite":
        transports = transport.get("transports") or {}
        children = list(transports.values()) if isinstance(transports, dict) else list(transports)
        results = [_evaluate(child, dd_site, winner, client_version) for child in children if isinstance(child, dict)]
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


def _resolve(environment: Variables, dd_site: str, provider_version: Optional[tuple], client_version: Optional[tuple]) -> _Resolution:
    for name in ("AIRFLOW__OPENLINEAGE__DISABLED", "OPENLINEAGE_DISABLED"):
        if name in environment and environment[name] is None:
            return _Resolution(ok=False, winner=name, unknown=f"whether {name} disables it")
        if (environment.get(name) or "").strip().lower() in _TRUE:
            return _Resolution(ok=False, winner=name, disables=True)

    conn_id_read = provider_version is None or provider_version >= PROVIDER_CONFIG_CONN_ID_VERSION
    if is_set(environment, "AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID") and conn_id_read:
        what = "the Airflow connection it names" if provider_version else "whether the installed provider reads it (2.18.0+), or that connection"
        return _Resolution(ok=False, winner="AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID", unknown=what)
    if is_set(environment, "AIRFLOW__OPENLINEAGE__CONFIG_PATH"):
        return _Resolution(ok=False, winner="AIRFLOW__OPENLINEAGE__CONFIG_PATH", unknown="the config file it points at")

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
    env_config = _env_style_config(environment)
    if is_set(environment, "OPENLINEAGE_CONFIG"):
        # the client merges that file between the env-style config and the config from 3.,
        # so it can only fill in keys 3. leaves unset. When the outcome is the same with no
        # file, a file filling every gap in Datadog's favour, and one filling every gap
        # against it, the file can't matter
        outcomes = [
            _select(_deep_merge(env_config, _deep_merge(file_config, user_config)), environment, dd_site, winner, client_version)
            for file_config in ({}, _helpful_config_file(dd_site), _HARMFUL_CONFIG_FILE)
        ]
        if len({outcome.ok for outcome in outcomes}) == 1 and not any(outcome.unknown for outcome in outcomes):
            # all failing with no file means the console fallback, which names nothing; the
            # Datadog-favouring file always yields a typed transport, so its outcome names the
            # explicit fragment (a URL, an auth) that no file could make work
            return outcomes[0] if outcomes[0].ok or outcomes[0].winner else outcomes[1]
        return _Resolution(ok=False, winner="OPENLINEAGE_CONFIG", unknown="the config file it points at")

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

    return _select(_deep_merge(env_config, user_config), environment, dd_site, winner, client_version)


def _json_object(raw: Any) -> Optional[dict]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _helpful_config_file(dd_site: str) -> dict:
    """A config file filling every gap with a transport to the intake -- the best a file could do."""
    http = {"type": "http", "url": f"https://data-obs-intake.{dd_site}", "auth": {"type": "api_key", "apiKey": "k", "apikey": "k", "api_key": "k"}}
    return {"transport": {**http, "transports": {"from_config_file": http}}}


#: A config file filling every gap against sending anywhere -- the worst a file could do.
_HARMFUL_CONFIG_FILE = {"transport": {"type": "console", "url": "https://from-config-file.invalid", "auth": {"type": "none"}, "transports": {}}}


def _select(config: dict, environment: Variables, dd_site: str, winner: Optional[str], client_version: Optional[tuple]) -> _Resolution:
    """openlineage-python's _resolve_transport steps 3, 5 and 6 on an already-merged config."""
    transport = config.get("transport")
    if isinstance(transport, dict) and transport.get("type"):
        return _evaluate(transport, dd_site, winner or "OPENLINEAGE__TRANSPORT__TYPE", client_version)
    if is_set(environment, "OPENLINEAGE_URL"):
        url = environment["OPENLINEAGE_URL"]
        api_key = environment.get("OPENLINEAGE_API_KEY")
        auth = {"type": "api_key", "apiKey": _UNKNOWN if api_key is None else api_key} if "OPENLINEAGE_API_KEY" in environment else None
        return _evaluate({"type": "http", "url": _UNKNOWN if url is None else url, "auth": auth}, dd_site, "OPENLINEAGE_URL", client_version)
    return _Resolution(ok=False, destinations=("the console -- no transport is configured",))


#: one standalone `export AIRFLOW__OPENLINEAGE__TRANSPORT=<one quoted or bare word>` -- nothing
#: else on the line, since patch_env_vars replaces the whole physical line
_STANDALONE_TRANSPORT_EXPORT = re.compile(
    rf"""\s*export\s+{_TRANSPORT_VAR}=(?:'[^']*'|"(?:[^"\\]|\\.)*"|[^\s'";&|#\\`$()<>]+)\s*"""
)


def transport_fields_to_set(dd_site: str) -> dict:
    """The fields a Datadog-bound transport gets corrected to -- the only part of it a plan ever carries."""
    return {"url": f"https://data-obs-intake.{dd_site}", "auth": {"type": "api_key", "apiKey": DD_API_KEY_PLACEHOLDER}}


def merge_transport_fields(startup_script_text: str, fields: str) -> Optional[str]:
    """startup.sh's AIRFLOW__OPENLINEAGE__TRANSPORT with `fields` (a plan's to_value) set in it; None if it isn't a JSON object now."""
    transport = _json_object(exported_environment(startup_script_text).get(_TRANSPORT_VAR))
    return None if transport is None else json.dumps({**transport, **json.loads(fields)})


def _datadog_transport_rewrite(
    environment: Variables, startup_script_text: Optional[str], dd_site: str, provider_version: Optional[tuple], client_version: Optional[tuple]
) -> Optional[str]:
    """The fields to set in AIRFLOW__OPENLINEAGE__TRANSPORT (JSON), if pointing it at this site's intake is a safe in-place fix.

    Only for a top-level http/async_http transport whose url is a Datadog intake,
    set by exactly one assignment in startup.sh, a standalone export line that's
    the value in effect (one patch_env_vars can replace) -- not
    airflow_configuration_options, which apply doesn't write. None unless the
    corrected transport would resolve. Only transport_fields_to_set is returned:
    the rest of the transport (headers, say) may hold credentials, so apply
    merges these fields into the transport it reads at apply time instead.
    """
    raw = environment.get(_TRANSPORT_VAR)
    script = startup_script_text or ""
    if raw is None or script.count(f"{_TRANSPORT_VAR}=") != 1:
        return None
    line = next(line for line in script.splitlines() if f"{_TRANSPORT_VAR}=" in line)
    if not _STANDALONE_TRANSPORT_EXPORT.fullmatch(line) or exported_environment(line).get(_TRANSPORT_VAR) != raw:
        return None
    transport = _json_object(raw)
    if transport is None or transport.get("type") not in ("http", "async_http") or not is_any_datadog_intake_url(transport.get("url")):
        return None
    fields = transport_fields_to_set(dd_site)
    if not _resolve({**environment, _TRANSPORT_VAR: json.dumps({**transport, **fields})}, dd_site, provider_version, client_version).ok:
        return None
    return json.dumps(fields)


def _installed_version(package: str, requirements_text: str, constraints_text: Optional[str]) -> Optional[tuple]:
    """The version pip will install, when it's pinned: requirements.txt (a pin or a wheel) first, else the constraints file."""
    for line in requirements_text.splitlines():
        if requirement_line_package(line) != package:
            continue
        pinned = re.search(r"==\s*([0-9][0-9.]*)", line) or re.search(r"-([0-9][0-9.]*)-py3-none-any\.whl", line)
        if pinned:
            return tuple(int(part) for part in pinned.group(1).strip(".").split("."))
    constrained = pinned_versions(constraints_text or "", package)
    if constrained and re.fullmatch(r"[0-9][0-9.]*", constrained[0]):
        return tuple(int(part) for part in constrained[0].strip(".").split("."))
    return None


def analyze(
    airflow_version: str,
    requirements_text: str,
    startup_script_text: Optional[str],
    configuration_options: dict,
    dd_site: str,
    constraints_text: Optional[str] = None,
) -> OpenLineageState:
    """constraints_text is the constraints file in effect, if known -- it pins what requirements.txt doesn't."""
    environment = effective_environment(startup_script_text, configuration_options)
    provider_version = _installed_version(OPENLINEAGE_PROVIDER, requirements_text, constraints_text)
    client_version = _installed_version("openlineage-python", requirements_text, constraints_text)
    resolution = _resolve(environment, dd_site, provider_version, client_version)
    issues: list[Finding] = []

    fixed = dict(environment)
    if not is_intake_url(fixed.get("OPENLINEAGE_URL"), dd_site):
        fixed["OPENLINEAGE_URL"] = f"https://data-obs-intake.{dd_site}"
    if not is_set(fixed, "OPENLINEAGE_API_KEY"):
        fixed["OPENLINEAGE_API_KEY"] = DD_API_KEY_PLACEHOLDER
    fixable = not resolution.ok and resolution.unknown is None and _resolve(fixed, dd_site, provider_version, client_version).ok
    rewrite = None
    if not resolution.ok and not fixable and resolution.unknown is None and resolution.winner == _TRANSPORT_VAR:
        rewrite = _datadog_transport_rewrite(environment, startup_script_text, dd_site, provider_version, client_version)

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
    elif not resolution.ok and not fixable and rewrite is None and resolution.winner:
        destinations = ", ".join(resolution.destinations)
        if resolution.winner == _TRANSPORT_VAR and is_any_datadog_intake_url((_json_object(environment.get(_TRANSPORT_VAR)) or {}).get("url")):
            # aimed at Datadog, but not somewhere apply can rewrite it
            message = f"{resolution.winner} sends OpenLineage events to {destinations}, and this can't correct it in place"
            detail = (
                f"It's set in airflow_configuration_options, or in a way the startup script can't be safely edited. Change its url "
                f"to https://data-obs-intake.{dd_site} with your API key, or remove it, then re-scan."
            )
        else:
            message = f"{resolution.winner} sends OpenLineage events to {destinations}, not to Datadog, and takes precedence over OPENLINEAGE_URL"
            detail = (
                "That's left alone: it's a choice of where events go. To send them to Datadog instead, remove "
                f"{resolution.winner} from the startup script / airflow_configuration_options, or point it at "
                f"https://data-obs-intake.{dd_site} with an API key, then re-scan."
            )
        issues.append(Finding("openlineage_transport", FindingStatus.FAIL, message, detail))

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

    existing_api_key = api_key_source = transport_key_rewrite = None
    api_key_site_changes = False
    api_key_editable = False
    if resolution.winner == "OPENLINEAGE_URL" or fixable:
        key = environment.get("OPENLINEAGE_API_KEY")
        if isinstance(key, str) and _LITERAL_API_KEY.fullmatch(key) and _effective_key_assignment_is_literal(startup_script_text or ""):
            existing_api_key, api_key_source = key, "OPENLINEAGE_API_KEY"
            api_key_editable = _single_standalone_key_export(startup_script_text or "")
            url = environment.get("OPENLINEAGE_URL")
            api_key_site_changes = is_any_datadog_intake_url(url) and not is_intake_url(url, dd_site)
    elif resolution.ok and resolution.winner == _TRANSPORT_VAR:
        auth = (_json_object(environment.get(_TRANSPORT_VAR)) or {}).get("auth")
        keys = {auth.get(name) for name in ("apiKey", "apikey", "api_key") if auth.get(name)} if isinstance(auth, dict) else set()
        key = next(iter(keys)) if len(keys) == 1 else None
        if isinstance(key, str) and _LITERAL_API_KEY.fullmatch(key):
            existing_api_key, api_key_source = key, _TRANSPORT_VAR
            transport_key_rewrite = _datadog_transport_rewrite(environment, startup_script_text, dd_site, provider_version, client_version)
            api_key_editable = transport_key_rewrite is not None

    workaround_ok = airflow_version not in VERSIONS_NEEDING_CONFIG_PATH_WORKAROUND or all(
        name in environment for name in ("AIRFLOW__OPENLINEAGE__CONFIG_PATH", "AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS")
    )
    configured = resolution.ok and provider_present and is_set(environment, "AIRFLOW__OPENLINEAGE__NAMESPACE") and workaround_ok
    return OpenLineageState(
        configured=configured,
        transport_fixable=fixable,
        issues=issues,
        environment=environment,
        transport_rewrite=rewrite,
        existing_api_key=existing_api_key,
        api_key_source=api_key_source,
        api_key_site_changes=api_key_site_changes,
        api_key_editable=api_key_editable,
        transport_key_rewrite=transport_key_rewrite,
    )

