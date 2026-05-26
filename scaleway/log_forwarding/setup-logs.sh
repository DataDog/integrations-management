#!/usr/bin/env bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

# ─────────────────────────────────────────────────────────────────────────────
# Scaleway Cloud Logs → Datadog  |  Setup Script
# ─────────────────────────────────────────────────────────────────────────────
#
# Sets up log forwarding from Scaleway to Datadog in three steps:
#
#   Step 0 – IAM Application Provisioning  (runs first, always)
#             Creates a dedicated least-privilege IAM application named
#             "datadog-integration" with an ObservabilityFullAccess policy,
#             generates an API key pair, and uses those credentials for all
#             subsequent API calls.  Idempotent — reuses the app if it exists.
#
#   Part 1 – Cockpit Native Exports
#             Forwards Scaleway product logs from all projects × regions to
#             Datadog using Scaleway Cockpit's built-in data exporter feature.
#             Requires no agent — Scaleway pushes logs directly.
#
#   Part 2 – Audit Trail Export  (optional, requires Docker)
#             Builds and deploys an OpenTelemetry Collector with the
#             scwaudittrail receiver to forward IAM/org-level audit events
#             to Datadog Logs.
#
#   Part 3 – Datadog Account Registration  (runs last, always)
#             Calls the Datadog API to create (or update) the Scaleway
#             integration account with the provisioned credentials.
#             No manual tile entry required.
#
# Prerequisites:
#   scw CLI            On Linux and macOS, the script offers to install and
#                       initialize it for you on first run via the official
#                       Scaleway install script.  On other platforms, install
#                       manually: https://github.com/scaleway/scaleway-cli
#                       The credentials provided to 'scw init' must have IAM
#                       Manager or Org Owner permissions (used only for Step 0)
#                       — generate a key at
#                       https://console.scaleway.com/iam/api-keys
#   curl, jq           (required for Part 1)
#   Docker, ssh, scp   (required for Part 2 — Docker daemon must be running
#                       on the host running this script; the collector binary
#                       is built locally before being deployed to the Instance)
#
# Usage:
#   export DD_API_KEY=...
#   export DD_APP_KEY=...
#   export DD_SITE=datadoghq.com
#   bash setup-logs.sh [--dry-run]
#
#   Scaleway credentials are read automatically from your scw CLI config.
#   Override any value by setting the corresponding environment variable.
#
#   --dry-run  Print every API call (method, URL, body) without executing it.
#              All env vars must still be set, but fake values are fine:
#                SCW_SECRET_KEY=x SCW_ACCESS_KEY=x SCW_PROJECT_ID=x \
#                DD_API_KEY=x DD_APP_KEY=x \
#                DD_SITE=datadoghq.com bash setup-logs.sh --dry-run
#
#   --teardown Delete the provisioned audit trail Instance (tagged
#              'datadog-audit-trail') and its IP/volumes, then exit.  Does
#              not touch IAM apps, Cockpit exporters, or the Datadog account.
#
# ── Configuration ─────────────────────────────────────────────────────────────
#
#   DD_API_KEY            Your Datadog API key                         [required]
#   DD_APP_KEY            Your Datadog application key                 [required]
#   DD_SITE               Your Datadog site                            [required]
#                         e.g. datadoghq.com, datadoghq.eu,
#                              us3.datadoghq.com, us5.datadoghq.com
#
#   SCW_SECRET_KEY        Scaleway IAM secret key  [default: from scw config]
#   SCW_ACCESS_KEY        Scaleway IAM access key  [default: from scw config]
#                         Generate a key pair at:
#                         https://console.scaleway.com/iam/api-keys
#                         (Or just let 'scw init' walk you through it.)
#
#   SCW_PROJECT_ID        Scaleway project ID to set up exports for    [default: from scw config]
#                         Only set this to target a non-default project.
#   SCALEWAY_REGIONS      Comma-separated Cockpit regions              [default: fr-par,nl-ams,pl-waw]
#   SCALEWAY_PRODUCTS     Comma-separated Scaleway products to export  [default: all]
#                         Use "all" to export every Cockpit-integrated product.
#                         Example: "kubernetes,rdb,object-storage"
#   SCW_AUDIT_TRAIL_ENABLED  Set up the audit trail collector          [default: true]
#                            Set by the integration tile UI's audit
#                            trail toggle.  When explicitly set, the
#                            provisioning prompt is suppressed (the
#                            UI toggle already implied consent).
#   SCW_INSTANCE_IP       IP of an existing Scaleway Instance to use   [default: auto-provision]
#                         If unset, the script provisions a new
#                         Instance (see PROVISION_INSTANCE below).
#   PROVISION_INSTANCE    Auto-provision an Instance for the audit     [default: auto, or
#                         trail when SCW_INSTANCE_IP is unset.          'true' if SCW_AUDIT_
#                         Values: 'auto' (prompts), 'true' (skip        TRAIL_ENABLED is
#                         prompt), 'false' (don't provision; skip       explicitly set]
#                         Part 2).
#   SCW_AUDIT_INSTANCE_TYPE  Commercial type for the provisioned Instance [default: DEV1-S]
#                            DEV1-S is ~€6.34/mo and available in all
#                            zones; STARDUST1-S in nl-ams-1 is cheaper
#                            (~€0.11/mo) when available.
#   SCW_AUDIT_INSTANCE_ZONE  Zone for the provisioned Instance         [default: ${SCW_REGION}-1]
#   SCW_AUDIT_INSTANCE_IMAGE Image label for the provisioned Instance  [default: ubuntu_jammy]
#   SCW_INSTANCE_USER     SSH user for the Instance                    [default: root]
#   SCW_ACCOUNT_NAME      Name for the Datadog integration account     [default: SCW_PROJECT_ID]
#
# For private-subnet audit-trail Instances, configure ProxyJump in
# ~/.ssh/config so the script's ssh/scp calls tunnel transparently:
#   Host my-private-vm
#       HostName <private-ip>
#       ProxyJump bastion@<gateway-ip>:61000
# See https://www.scaleway.com/en/docs/public-gateways/how-to/use-ssh-bastion/
#
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Flags ─────────────────────────────────────────────────────────────────────
DRY_RUN=false
TEARDOWN=false
for _arg in "$@"; do
  case "$_arg" in
    --dry-run)  DRY_RUN=true ;;
    --teardown) TEARDOWN=true ;;
  esac
done
unset _arg

# ── Logging helpers ───────────────────────────────────────────────────────────
# Defined early so bootstrap_scw and everything below can use them.
_ts()    { date '+%H:%M:%S'; }
log()    { printf '\033[0;34m[%s]\033[0m  %s\n'    "$(_ts)" "$*"; }
ok()     { printf '\033[0;32m[%s] ✓\033[0m  %s\n' "$(_ts)" "$*"; }
warn()   { printf '\033[0;33m[%s] ⚠\033[0m  %s\n' "$(_ts)" "$*" >&2; }
die()    { printf '\033[0;31m[%s] ✗\033[0m  %s\n' "$(_ts)" "$*" >&2; exit 1; }
dryrun() { printf '\033[0;35m[%s] ~\033[0m  %s\n' "$(_ts)" "$*" >&2; }

# Prompt with a default-yes [Y/n] confirmation.  Returns 0 unless the user
# explicitly answered N/n.  Reads from /dev/tty so it works under `bash <(curl …)`.
confirm_default_yes() {
  local prompt="$1" ans=""
  printf '  %s [Y/n] ' "$prompt" >&2
  read -r ans </dev/tty || true
  [[ ! "$ans" =~ ^[Nn]$ ]]
}

# ── Bootstrap: ensure scw CLI is installed and initialized ───────────────────
# On Linux and macOS, offers to install scw via the official Scaleway install
# script if it's missing, then runs `scw init` interactively when no
# credentials are configured.  On other platforms (BSDs, etc.), prints manual
# install instructions and exits.
#
# Skipped in --dry-run: prints what *would* happen but doesn't modify the
# system or open interactive prompts.  Callers running --dry-run are expected
# to provide SCW_SECRET_KEY / SCW_ACCESS_KEY / SCW_ORGANIZATION_ID via env var.
SCW_INSTALL_URL="https://raw.githubusercontent.com/scaleway/scaleway-cli/master/scripts/get.sh"
SCW_DOCS_INSTALL_URL="https://www.scaleway.com/en/docs/developer-tools/scaleway-cli/reference-content/install-cli/"
SCW_CONSOLE_KEYS_URL="https://console.scaleway.com/iam/api-keys"

# Fetch the latest scw binary from Scaleway's GitHub releases and install it
# to /usr/local/bin.  Used on macOS when Homebrew isn't available — covers
# Apple Silicon, which Scaleway's get.sh script doesn't.
_install_scw_darwin_direct() {
  confirm_default_yes "Download the official Scaleway binary and install it now?" \
    || die "Aborting.  Install scw manually and re-run."

  local arch tag binary_url tmpdir
  arch=$(uname -m); [[ "$arch" == "x86_64" ]] && arch="amd64"
  # Resolve the latest tag via HTTP redirect, not the GH API — anon API calls
  # are rate-limited to 60/hr/IP and the redirect endpoint isn't.
  tag=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
    https://github.com/scaleway/scaleway-cli/releases/latest 2>/dev/null \
    | sed 's|.*/tag/||')
  [[ -n "$tag" ]] || die "Failed to look up scw latest release.  See ${SCW_DOCS_INSTALL_URL}"

  binary_url="https://github.com/scaleway/scaleway-cli/releases/download/${tag}/scaleway-cli_${tag#v}_darwin_${arch}"
  tmpdir=$(mktemp -d) || die "Failed to create temp dir."
  trap 'rm -rf "$tmpdir"' RETURN

  log "Downloading scw ${tag} for darwin/${arch}..."
  curl -fsSL -o "$tmpdir/scw" "$binary_url" \
    || die "Failed to download scw from ${binary_url}"
  chmod +x "$tmpdir/scw"

  if [[ -w /usr/local/bin ]]; then
    mv "$tmpdir/scw" /usr/local/bin/scw
  else
    log "Installing scw to /usr/local/bin (sudo required)..."
    sudo mkdir -p /usr/local/bin && sudo mv "$tmpdir/scw" /usr/local/bin/scw \
      || die "Install failed.  See ${SCW_DOCS_INSTALL_URL}"
  fi
}

bootstrap_scw() {
  if ! command -v scw &>/dev/null; then
    if [[ "$DRY_RUN" == "true" ]]; then
      dryrun "scw CLI not found — would prompt to install."
      return 0
    fi

    local os; os=$(uname -s)

    case "$os" in
      Linux)
        warn "scw CLI not found."
        confirm_default_yes "Install it now via the official Scaleway install script? (${SCW_INSTALL_URL})" \
          || die "Aborting.  Install scw manually and re-run."
        curl -fsSL "$SCW_INSTALL_URL" | sh \
          || die "scw install failed.  See ${SCW_DOCS_INSTALL_URL}"
        ;;
      Darwin)
        # On macOS prefer Homebrew when available; otherwise fall back to the
        # direct binary download (which handles Apple Silicon, unlike get.sh).
        warn "scw CLI not found."
        if command -v brew &>/dev/null; then
          confirm_default_yes "Install it now via Homebrew (brew install scw)?" \
            || die "Aborting.  Install scw manually and re-run."
          brew install scw \
            || die "brew install scw failed.  See ${SCW_DOCS_INSTALL_URL}"
        else
          _install_scw_darwin_direct
        fi
        ;;
      *)
        die "scw CLI not found.
  Auto-install is supported on Linux and macOS; on $os install manually:
    ${SCW_DOCS_INSTALL_URL}
  Then run: scw init"
        ;;
    esac

    command -v scw &>/dev/null \
      || die "scw was installed but is not on PATH.  Open a new shell (or add the install dir to PATH) and re-run."
  fi

  # scw is installed.  Decide whether to run `scw init`:
  #   - skip if SCW_SECRET_KEY is already set via env var
  #   - skip if `scw config` already has a secret-key
  #   - otherwise run scw init interactively so the user is prompted for creds
  [[ -n "${SCW_SECRET_KEY:-}" ]] && return 0
  [[ -n "$(scw config get secret-key 2>/dev/null || true)" ]] && return 0

  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "scw is not initialized — would run \`scw init\`."
    return 0
  fi

  warn "scw CLI is not initialized — running \`scw init\`."
  log "You will be prompted for your Scaleway access key and secret key."
  log "Generate them at: ${SCW_CONSOLE_KEYS_URL}"
  scw init </dev/tty || die "\`scw init\` failed.  Re-run when ready."
}

bootstrap_scw

# ── Scaleway credentials — read from scw config, overridable via env ──────────
scw_config_get() { scw config get "$1" 2>/dev/null || true; }

SCW_SECRET_KEY="${SCW_SECRET_KEY:-$(scw_config_get secret-key)}"
SCW_ACCESS_KEY="${SCW_ACCESS_KEY:-$(scw_config_get access-key)}"
SCW_ORGANIZATION_ID="${SCW_ORGANIZATION_ID:-$(scw_config_get default-organization-id)}"

# ── Datadog — must be set explicitly ─────────────────────────────────────────
: "${DD_API_KEY:?DD_API_KEY is required (your Datadog API key)}"
: "${DD_APP_KEY:?DD_APP_KEY is required (your Datadog application key)}"
: "${DD_SITE:?DD_SITE is required (e.g. datadoghq.com)}"

# ── Optional / defaults ───────────────────────────────────────────────────────
SCW_PROJECT_ID="${SCW_PROJECT_ID:-$(scw_config_get default-project-id)}"
# Parses supported Cockpit regions from the scw CLI help text so new regions
# are picked up automatically when the CLI is updated, without needing changes
# here.  Relies on the "(fr-par | nl-ams | ...)" format of the help output —
# if Scaleway changes that format the parse silently falls back to the
# hardcoded list below.
_scw_cockpit_regions() {
  local regions
  regions=$(scw cockpit data-source list --help 2>&1 \
    | grep 'region=' | sed 's/.*(\(.*\))/\1/' \
    | tr '|' '\n' | tr -d ' ' | grep -Ev '^$|^all$' \
    | paste -sd ',') || true
  echo "${regions:-fr-par,nl-ams,pl-waw}"
}
SCALEWAY_REGIONS="${SCALEWAY_REGIONS:-$(_scw_cockpit_regions)}"
SCALEWAY_PRODUCTS="${SCALEWAY_PRODUCTS:-all}"            # "all" or CSV of Cockpit product names (e.g. "kubernetes,rdb")
# SCW_AUDIT_TRAIL_ENABLED is the field the integration tile UI sets via its
# "Collect Scaleway audit trail logs" toggle.  When explicitly set (UI flow
# or scripted use), treat it as user consent to provision an Instance so the
# provisioning prompt is suppressed; the user already opted in at the toggle.
# When unset (interactive user running the script directly), default to true
# and let PROVISION_INSTANCE=auto drive the normal prompt flow.
if [[ "${SCW_AUDIT_TRAIL_ENABLED:-}" == "true" ]]; then
  : "${PROVISION_INSTANCE:=true}"
fi
SCW_AUDIT_TRAIL_ENABLED="${SCW_AUDIT_TRAIL_ENABLED:-true}"
SCW_REGION="${SCW_REGION:-$(scw_config_get default-region)}"
SCW_REGION="${SCW_REGION:-fr-par}"        # fallback if not configured
SCW_INSTANCE_IP="${SCW_INSTANCE_IP:-}"       # IP of the Scaleway Instance for audit trail (auto-provisioned if empty)
SCW_INSTANCE_USER="${SCW_INSTANCE_USER:-root}" # SSH user for the Instance (default: root)
SCW_ACCOUNT_NAME="${SCW_ACCOUNT_NAME:-}" # defaults to SCW_PROJECT_ID at registration time

# Auto-provisioning settings — used when SCW_INSTANCE_IP is empty.
PROVISION_INSTANCE="${PROVISION_INSTANCE:-auto}"                   # auto | true | false
SCW_AUDIT_INSTANCE_TYPE="${SCW_AUDIT_INSTANCE_TYPE:-DEV1-S}"       # cheapest universally-available type
SCW_AUDIT_INSTANCE_ZONE="${SCW_AUDIT_INSTANCE_ZONE:-${SCW_REGION}-1}"
SCW_AUDIT_INSTANCE_IMAGE="${SCW_AUDIT_INSTANCE_IMAGE:-ubuntu_jammy}"
AUDIT_INSTANCE_TAG="datadog-audit-trail"                            # used for find-or-create, instance name, and --teardown

SCW_API="https://api.scaleway.com"
EXPORTER_NAME="${EXPORTER_NAME:-datadog-logs-${DD_SITE}}" # one exporter per Datadog datacenter
IAM_APP_NAME="datadog-integration"
IAM_POLICY_NAME="datadog-integration-policy"
IAM_ACCESS_KEY=""
IAM_SECRET_KEY=""
_IAM_OLD_KEYS=""
_AUDIT_DEPLOYED=false
# True when a collector might already be running with an existing key
# (tagged Instance from a prior run, or BYO SCW_INSTANCE_IP).  Gates the
# end-of-run cleanup so we don't revoke a key the live collector still uses.
_PRE_EXISTING_AUDIT_INSTANCE=false
# Cockpit Part 1 outcomes — used in main() to decide whether to register the
# Datadog account.  If nothing worked, we skip Part 3 to avoid leaving a
# dangling integration entry with no data flowing.
_COCKPIT_CREATED=0
_COCKPIT_SKIPPED=0
_COCKPIT_FAILED=0
# Stashed original (owner-level) creds.  provision_iam_application swaps the
# bash-local SCW_*_KEY vars to the new app's keys so the rest of the script
# runs least-privileged.  The end-of-run IAM key cleanup needs the original
# (write-capable) creds to actually be able to delete old keys.
_ORIG_SCW_ACCESS_KEY=""
_ORIG_SCW_SECRET_KEY=""
# SKIP_IAM and MULTISITE_CREDS_FILE are internal hooks for multi-site testing
# — set when reusing credentials provisioned by a prior run against another site.
SKIP_IAM="${SKIP_IAM:-false}"
MULTISITE_CREDS_FILE="${MULTISITE_CREDS_FILE:-}"

# Stub JSON returned by all API helpers in dry-run mode.  Contains enough
# fields to satisfy every jq query in this script; empty arrays mean "nothing
# found" so create-or-update paths always take the create branch.
_DRY_RUN_STUB='{"id":"dry-run-id","access_key":"DRY_RUN_ACCESS_KEY","secret_key":"DRY_RUN_SECRET_KEY","status":"active","applications":[],"policies":[],"api_keys":[],"total_count":0,"data_sources":[],"exporters":[],"data":[]}'

# ── Scaleway API helpers ──────────────────────────────────────────────────────
scw_request() {
  local method="$1" path="$2" body="${3:-}"
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "${method} ${SCW_API}${path}"
    [[ -n "$body" ]] && dryrun "body ${body}"
    echo "$_DRY_RUN_STUB"; return
  fi
  # -g disables curl URL globbing so query params with [] (e.g. page[limit]) pass through verbatim.
  local args=(-sS -g -w $'\n%{http_code}' -H "X-Auth-Token: $SCW_SECRET_KEY")
  [[ "$method" != "GET" ]] && args+=(-X "$method" -H "Content-Type: application/json" -d "$body")
  local resp
  resp=$(curl "${args[@]}" "${SCW_API}${path}")
  local http_code="${resp##*$'\n'}" body_out="${resp%$'\n'*}"
  if [[ "$http_code" -ge 400 ]]; then
    printf '%s\n' "$body_out" >&2; return 1
  fi
  printf '%s\n' "$body_out"
}

scw_get()  { scw_request GET  "$1"; }
scw_post() { scw_request POST "$1" "$2"; }

# ── Datadog API helpers ───────────────────────────────────────────────────────
dd_request() {
  local method="$1" path="$2" body="${3:-}"
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "${method} https://api.${DD_SITE}${path}"
    [[ -n "$body" ]] && dryrun "body ${body}"
    echo "$_DRY_RUN_STUB"; return
  fi
  # -g disables curl URL globbing so query params with [] (e.g. page[limit]) pass through verbatim.
  local args=(-sS -g -w $'\n%{http_code}'
    -H "DD-API-KEY: $DD_API_KEY"
    -H "DD-APPLICATION-KEY: $DD_APP_KEY")
  [[ "$method" != "GET" ]] && args+=(-X "$method" -H "Content-Type: application/json" -d "$body")
  local resp
  resp=$(curl "${args[@]}" "https://api.${DD_SITE}${path}")
  local http_code="${resp##*$'\n'}" body_out="${resp%$'\n'*}"
  if [[ "$http_code" -ge 400 ]]; then
    printf '%s\n' "$body_out" >&2; return 1
  fi
  printf '%s\n' "$body_out"
}

dd_get()   { dd_request GET   "$1"; }
dd_post()  { dd_request POST  "$1" "$2"; }
dd_patch() { dd_request PATCH "$1" "$2"; }

# Fetches all pages from a Datadog list endpoint (page[limit]/page[offset]).
# Returns {"data": [...]} with every item from every page merged.
dd_get_all() {
  local path="$1"
  local limit=100 offset=0
  local sep='?'; [[ "$path" == *'?'* ]] && sep='&'
  local all_items='[]'
  while true; do
    local resp items count
    resp=$(dd_get "${path}${sep}page[limit]=${limit}&page[offset]=${offset}") || return 1
    items=$(jq '.data // []' <<< "$resp")
    count=$(jq 'length' <<< "$items")
    all_items=$(jq -n --argjson a "$all_items" --argjson b "$items" '$a + $b')
    (( count < limit )) && break
    (( offset += limit ))
  done
  jq -n --argjson data "$all_items" '{"data": $data}'
}

# ── Prerequisites check ───────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  command -v curl &>/dev/null || missing+=(curl)
  command -v jq   &>/dev/null || missing+=(jq)
  command -v scw  &>/dev/null || missing+=(scw)
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required tools: ${missing[*]}
  Install with:
    macOS:   brew install ${missing[*]}
    Linux:   apt-get install -y ${missing[*]}   (or your distro's equivalent)
  Then re-run this script."
  fi

  if [[ "$SCW_AUDIT_TRAIL_ENABLED" == "true" ]]; then
    local audit_missing=()
    command -v docker &>/dev/null || audit_missing+=(docker)
    command -v ssh    &>/dev/null || audit_missing+=(ssh)
    command -v scp    &>/dev/null || audit_missing+=(scp)
    if [[ ${#audit_missing[@]} -gt 0 ]]; then
      warn "Audit trail (Part 2) requires: ${audit_missing[*]}"
      for tool in "${audit_missing[@]}"; do
        case "$tool" in
          docker) warn "  docker: https://docs.docker.com/get-docker/" ;;
          ssh|scp) warn "  ssh/scp: install OpenSSH (macOS: built-in, Linux: apt-get install openssh-client)" ;;
        esac
      done
      warn "  Set SCW_AUDIT_TRAIL_ENABLED=false to skip Part 2 and suppress this warning."
      SCW_AUDIT_TRAIL_ENABLED="false"
    fi
  fi

  log "Prerequisites OK"
}

# ── Datadog API permission pre-flight ────────────────────────────────────────
# Verifies the supplied DD_API_KEY/DD_APP_KEY can write Scaleway integration
# accounts (the `integrations_manage` permission), without side effects.
#
# We probe with a DELETE on an all-zero UUID.  Datadog applies auth and
# permission checks before the existence check, so:
#   - 401 -> bad keys
#   - 403 -> missing `integrations_manage`
#   - 404 -> auth OK, permission OK, account not found (the success signal)
#   - 2xx -> theoretically impossible with an all-zero UUID
#
# This is more accurate than a GET probe (which Datadog gates on a separate
# read permission, false-negative-ing users who have write but not read).
#
# Run before any Scaleway-side work so a permission failure doesn't leave the
# user with half-provisioned IAM apps, exporters, or Instances.
preflight_check_datadog_access() {
  log "Verifying Datadog API key can manage Scaleway integration accounts..."

  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "DELETE https://api.${DD_SITE}/api/v2/web-integrations/scaleway/accounts/<probe-uuid> (pre-flight)"
    return 0
  fi

  # Zero-UUID is structurally valid but vanishingly unlikely to correspond to
  # a real account, so the DELETE is a no-op.
  local probe_id="00000000-0000-0000-0000-000000000000"
  local resp http_code body_out
  resp=$(curl -sS -g -X DELETE -w $'\n%{http_code}' \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    "https://api.${DD_SITE}/api/v2/web-integrations/scaleway/accounts/${probe_id}" 2>&1) \
    || die "Could not reach Datadog API at https://api.${DD_SITE} — check DD_SITE and network connectivity."

  http_code="${resp##*$'\n'}"
  body_out="${resp%$'\n'*}"

  case "$http_code" in
    401)
      die "Datadog returned 401 Unauthorized.
  Verify DD_API_KEY and DD_APP_KEY are valid keys for site ${DD_SITE}.
  No Scaleway resources have been created."
      ;;
    403)
      die "Datadog returned 403 Forbidden — your API/App key lacks the
  'integrations_manage' permission required to register the Scaleway
  integration account.

  Fix one of:
    - Ask a Datadog admin to grant your role 'integrations_manage'
      (Organization Settings -> Roles -> your role -> Integrations -> Manage).
    - Re-run with credentials from a user who has that permission.

  No Scaleway resources have been created — safe to re-run after fixing."
      ;;
    404|4[0-9][0-9]|2??)
      # 404 = expected (no such account).  Other 4xx codes (e.g. 400 for path
      # validation, 422) and 2xx still imply auth/permission passed.
      ok "Datadog API write access verified"
      ;;
    *)
      die "Datadog returned unexpected status ${http_code} from
  /api/v2/web-integrations/scaleway/accounts:
  ${body_out}
  No Scaleway resources have been created."
      ;;
  esac
}

# Confirms at least one Scaleway IAM SSH key is registered before any
# Scaleway-side work runs.  The audit trail collector is deployed over SSH to a
# new Instance, and Scaleway auto-installs registered IAM SSH keys on Instance
# creation — without one, the script would provision the Instance and then fail
# at SSH-keyscan time, leaving the Instance orphaned.
#
# Only relevant when audit trail provisioning will actually run (toggle on, no
# BYO IP, provisioning not disabled).  Caller gates this in main().
preflight_check_scaleway_ssh_key() {
  log "Verifying a Scaleway IAM SSH key is registered for audit trail provisioning..."

  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "scw iam ssh-key list (pre-flight)"
    return 0
  fi

  local key_count
  key_count=$(scw iam ssh-key list project-id="$SCW_PROJECT_ID" -o json 2>/dev/null | jq 'length')
  if [[ "${key_count:-0}" -lt 1 ]]; then
    die "No SSH keys are registered in your Scaleway account.
  The audit trail collector is deployed over SSH to a new Scaleway Instance,
  and Scaleway auto-installs registered IAM SSH keys on Instance creation.

  Fix one of:
    - Run: scw iam ssh-key init    (registers your local ~/.ssh/id_*.pub)
    - Disable audit trail by setting SCW_AUDIT_TRAIL_ENABLED=false.
    - Or supply an existing Instance via SCW_INSTANCE_IP to skip provisioning.

  No Scaleway resources have been created — safe to re-run after fixing."
  fi

  ok "Scaleway SSH key check passed (${key_count} registered)"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 0: IAM Application Provisioning
# ─────────────────────────────────────────────────────────────────────────────
# Creates (or reuses) a dedicated IAM application for the Datadog integration,
# attaches an ObservabilityFullAccess policy scoped to the organisation, and
# generates a fresh API key pair.  After this function returns, SCW_ACCESS_KEY
# and SCW_SECRET_KEY hold the application credentials so all subsequent calls
# run under least-privilege permissions.

provision_iam_application() {
  log "━━━ Step 0: Provisioning IAM Application ━━━"

  : "${SCW_ORGANIZATION_ID:?SCW_ORGANIZATION_ID not found. Run 'scw init' or set SCW_ORGANIZATION_ID.}"
  : "${SCW_PROJECT_ID:?SCW_PROJECT_ID not set. Run 'scw init' to set a default project, or set SCW_PROJECT_ID explicitly.}"

  # Stash the original (owner-level) creds before any swap.  Used at end-of-run
  # to delete old IAM keys — the app creds we swap to below lack IAM write.
  _ORIG_SCW_ACCESS_KEY="$SCW_ACCESS_KEY"
  _ORIG_SCW_SECRET_KEY="$SCW_SECRET_KEY"

  log "Checking for existing IAM application '${IAM_APP_NAME}'..."
  local apps_resp app_id
  apps_resp=$(scw_get "/iam/v1alpha1/applications?organization_id=${SCW_ORGANIZATION_ID}&name=${IAM_APP_NAME}&page_size=100") \
    || die "Failed to list IAM applications"
  app_id=$(jq -r --arg name "$IAM_APP_NAME" \
    'first(.applications[] | select(.name == $name) | .id) // empty' <<< "$apps_resp")

  if [[ -n "$app_id" ]]; then
    ok "Reusing existing IAM application '${IAM_APP_NAME}' (id=${app_id})"
  else
    log "Creating IAM application '${IAM_APP_NAME}'..."
    local app_body app_resp
    app_body=$(jq -n \
      --arg name "$IAM_APP_NAME" \
      --arg org  "$SCW_ORGANIZATION_ID" \
      '{"name": $name, "organization_id": $org, "description": "Datadog integration service account"}')
    app_resp=$(scw_post "/iam/v1alpha1/applications" "$app_body") \
      || die "Failed to create IAM application"
    app_id=$(jq -r '.id' <<< "$app_resp")
    ok "Created IAM application '${IAM_APP_NAME}' (id=${app_id})"
  fi

  log "Checking for existing IAM policy '${IAM_POLICY_NAME}'..."
  local policies_resp policy_id
  policies_resp=$(scw_get "/iam/v1alpha1/policies?organization_id=${SCW_ORGANIZATION_ID}&application_id=${app_id}&page_size=100") \
    || die "Failed to list IAM policies"
  policy_id=$(jq -r --arg name "$IAM_POLICY_NAME" --arg app_id "$app_id" \
    'first(.policies[] | select(.name == $name and .application_id == $app_id) | .id) // empty' <<< "$policies_resp")

  local rules_json
  rules_json=$(jq -n \
    --arg org        "$SCW_ORGANIZATION_ID" \
    --arg project_id "$SCW_PROJECT_ID" \
    '[
      {
        permission_set_names: ["ObservabilityFullAccess", "AllProductsReadOnly"],
        project_ids:          [$project_id]
      },
      {
        permission_set_names: ["AuditTrailReadOnly"],
        organization_id:      $org
      }
    ]')

  if [[ -z "$policy_id" ]]; then
    log "Creating IAM policy '${IAM_POLICY_NAME}'..."
    local policy_body policy_resp
    policy_body=$(jq -n \
      --arg name       "$IAM_POLICY_NAME" \
      --arg org        "$SCW_ORGANIZATION_ID" \
      --arg app_id     "$app_id" \
      --argjson rules  "$rules_json" \
      '{name: $name, organization_id: $org, application_id: $app_id, rules: $rules}')
    policy_resp=$(scw_post "/iam/v1alpha1/policies" "$policy_body") \
      || die "Failed to create IAM policy — fix the error above and re-run the script"
    policy_id=$(jq -r '.id' <<< "$policy_resp")
    ok "Created IAM policy '${IAM_POLICY_NAME}' (id=${policy_id})"
  fi

  # Always refresh rules via the dedicated endpoint.  Scaleway's policy PATCH
  # only accepts name/description/tags/principal — the `rules` field is
  # silently dropped on PATCH, so to ensure rules are current on re-runs we
  # call PUT /iam/v1alpha1/rules (which replaces the policy's full rule set).
  log "Setting IAM policy rules..."
  local rules_body
  rules_body=$(jq -n --arg policy_id "$policy_id" --argjson rules "$rules_json" \
    '{policy_id: $policy_id, rules: $rules}')
  scw_request PUT "/iam/v1alpha1/rules" "$rules_body" >/dev/null \
    || die "Failed to set IAM policy rules"
  ok "IAM policy rules set (id=${policy_id})"

  log "Generating API key for application '${IAM_APP_NAME}'..."
  local key_body key_resp
  key_body=$(jq -n \
    --arg app_id "$app_id" \
    '{"application_id": $app_id, "description": "Datadog integration setup"}')
  key_resp=$(scw_post "/iam/v1alpha1/api-keys" "$key_body") \
    || die "Failed to create API key"
  IFS=$'\t' read -r IAM_ACCESS_KEY IAM_SECRET_KEY \
    < <(jq -r '[.access_key, .secret_key] | @tsv' <<< "$key_resp")
  ok "Generated API key (access_key=${IAM_ACCESS_KEY})"

  # Stage old keys for cleanup — deleted only after account registration succeeds
  # so a failed registration doesn't revoke the key Datadog was already using.
  _IAM_OLD_KEYS=$(scw iam api-key list "bearer-id=${app_id}" bearer-type=application \
    "organization-id=${SCW_ORGANIZATION_ID}" --output json 2>/dev/null \
    | jq -r --arg new_key "$IAM_ACCESS_KEY" '.[] | select(.access_key != $new_key) | .access_key' \
    2>/dev/null) || true

  SCW_ACCESS_KEY="$IAM_ACCESS_KEY"
  SCW_SECRET_KEY="$IAM_SECRET_KEY"
  log "Switched to application credentials for remaining setup."

  if [[ -n "$MULTISITE_CREDS_FILE" ]]; then
    (umask 077; printf 'SCW_ACCESS_KEY=%s\nSCW_SECRET_KEY=%s\n' "$IAM_ACCESS_KEY" "$IAM_SECRET_KEY" > "$MULTISITE_CREDS_FILE")
  fi
  echo
}

# Prints the provisioned Scaleway credentials for safekeeping.
print_datadog_credentials() {
  printf '\n'
  printf '\033[0;32m╔══════════════════════════════════════════════════════════════╗\033[0m\n'
  printf '\033[0;32m║          Scaleway IAM Credentials — keep these safe         ║\033[0m\n'
  printf '\033[0;32m╚══════════════════════════════════════════════════════════════╝\033[0m\n'
  printf '\n'
  printf '  %-20s  %s\n' "Access Key:"      "$IAM_ACCESS_KEY"
  printf '  %-20s  %s\n' "Secret Key:"      "$IAM_SECRET_KEY"
  printf '  %-20s  %s\n' "Project ID:"      "$SCW_PROJECT_ID"
  printf '  %-20s  %s\n' "Organization ID:" "$SCW_ORGANIZATION_ID"
  printf '\n'
  printf '\033[0;33m  ⚠  The Secret Key cannot be retrieved again after this session.\033[0m\n'
  printf '\n'
}

# ─────────────────────────────────────────────────────────────────────────────
# Part 3: Datadog Account Registration
# ─────────────────────────────────────────────────────────────────────────────

register_datadog_account() {
  log "━━━ Part 3: Registering Datadog Scaleway Account ━━━"

  local account_name="${SCW_ACCOUNT_NAME:-$SCW_PROJECT_ID}"

  local payload
  payload=$(jq -n \
    --arg name "$account_name" \
    --arg proj "$SCW_PROJECT_ID" \
    --arg org  "$SCW_ORGANIZATION_ID" \
    --arg ak   "$IAM_ACCESS_KEY" \
    --arg sk   "$IAM_SECRET_KEY" \
    '{
      data: {
        type: "Account",
        attributes: {
          name: $name,
          settings: {
            project_id:      $proj,
            organization_id: $org
          },
          secrets: {
            access_key: $ak,
            secret_key: $sk
          }
        }
      }
    }')

  log "Checking for existing Datadog Scaleway account '${account_name}'..."
  local accounts_resp account_id
  accounts_resp=$(dd_get_all "/api/v2/web-integrations/scaleway/accounts") \
    || die "Failed to list Datadog Scaleway accounts"
  account_id=$(jq -r --arg name "$account_name" \
    'first(.data[] | select(.attributes.name == $name) | .id) // empty' <<< "$accounts_resp")

  local action_resp
  if [[ -n "$account_id" ]]; then
    log "Account exists — updating (id=${account_id})..."
    action_resp=$(dd_patch "/api/v2/web-integrations/scaleway/accounts/${account_id}" "$payload") \
      || die "Failed to update Datadog Scaleway account"
    account_id=$(jq -r 'if (.data | type) == "object" then .data.id // "dry-run-id" else (.id // "dry-run-id") end' <<< "$action_resp")
    ok "Updated Datadog Scaleway account '${account_name}' (id=${account_id})"
  else
    log "Creating Datadog Scaleway account '${account_name}'..."
    action_resp=$(dd_post "/api/v2/web-integrations/scaleway/accounts" "$payload") \
      || die "Failed to create Datadog Scaleway account"
    account_id=$(jq -r 'if (.data | type) == "object" then .data.id // "dry-run-id" else (.id // "dry-run-id") end' <<< "$action_resp")
    ok "Created Datadog Scaleway account '${account_name}' (id=${account_id})"
  fi

  echo
  ok "Integration is now active  account=${account_name}  id=${account_id}"
  echo
}

# ─────────────────────────────────────────────────────────────────────────────
# Part 1: Cockpit Native Data Exports
# ─────────────────────────────────────────────────────────────────────────────

# origin=scaleway filters out user-created custom data sources.
get_log_datasource_ids() {
  local project_id="$1" region="$2"
  scw_get "/cockpit/v1/regions/${region}/data-sources?project_id=${project_id}&origin=scaleway&types=logs&page_size=100" \
    | jq -r '.data_sources[].id // empty'
}

# Returns the datasource IDs of every existing exporter named $EXPORTER_NAME
# in the region. One list call covers all data sources — avoids an N+1 check.
get_exported_datasource_ids() {
  local region="$1" project_id="$2"
  scw_get "/cockpit/v1/regions/${region}/exporters?project_id=${project_id}&page_size=100" \
    | jq -r --arg name "$EXPORTER_NAME" '.exporters[] | select(.name == $name) | .datasource_id'
}

create_exporter() {
  local datasource_id="$1" region="$2" project_id="$3"

  local products_json
  if [[ "$SCALEWAY_PRODUCTS" == "all" ]]; then
    products_json='["all"]'
  else
    products_json=$(printf '%s' "$SCALEWAY_PRODUCTS" | jq -Rcs 'split(",") | map(ltrimstr(" ") | rtrimstr(" "))')
  fi

  local body
  body=$(jq -n \
    --arg  name     "$EXPORTER_NAME" \
    --arg  ds_id    "$datasource_id" \
    --arg  api_key  "$DD_API_KEY" \
    --arg  endpoint "https://http-intake.logs.${DD_SITE}" \
    --argjson prods "$products_json" \
    '{
      name:              $name,
      datasource_id:     $ds_id,
      exported_products: $prods,
      datadog_destination: {
        api_key:  $api_key,
        endpoint: $endpoint
      }
    }')

  local resp
  if resp=$(scw_post "/cockpit/v1/regions/${region}/exporters" "$body" 2>&1); then
    local status
    status=$(jq -r '.status // "unknown"' <<< "$resp")
    ok "Exporter created  project=$project_id  region=$region  datasource=$datasource_id  status=$status"
    return 0
  else
    warn "Failed to create exporter  project=$project_id  region=$region  datasource=$datasource_id"
    warn "Response: $resp"
    return 1
  fi
}

setup_cockpit_exports() {
  log "━━━ Part 1: Cockpit Native Data Exports ━━━"

  IFS=',' read -ra regions <<< "$SCALEWAY_REGIONS"

  log "Project: $SCW_PROJECT_ID | Regions: ${regions[*]} | Products: $SCALEWAY_PRODUCTS"
  echo

  local created=0 skipped=0 failed=0

  for region in "${regions[@]}"; do
    local datasource_ids=()
    while IFS= read -r _id; do
      [[ -n "$_id" ]] && datasource_ids+=("$_id")
    done < <(get_log_datasource_ids "$SCW_PROJECT_ID" "$region" 2>/dev/null || true)

    if [[ ${#datasource_ids[@]} -eq 0 ]]; then
      warn "No Scaleway log data sources found  project=$SCW_PROJECT_ID  region=$region — skipping"
      skipped=$((skipped + 1))
      continue
    fi

    local exported_ids
    exported_ids=$(get_exported_datasource_ids "$region" "$SCW_PROJECT_ID" 2>/dev/null || echo "")

    for ds_id in "${datasource_ids[@]}"; do
      if grep -qxF "$ds_id" <<< "$exported_ids"; then
        ok "Already exported  project=$SCW_PROJECT_ID  region=$region  datasource=$ds_id"
        skipped=$((skipped + 1))
      elif create_exporter "$ds_id" "$region" "$SCW_PROJECT_ID"; then
        created=$((created + 1))
      else
        failed=$((failed + 1))
      fi
    done
  done

  echo
  log "Cockpit exports: $created created, $skipped already existed / no data, $failed failed"
  [[ $failed -eq 0 ]] || warn "$failed exporter(s) failed — check output above"

  _COCKPIT_CREATED=$created
  _COCKPIT_SKIPPED=$skipped
  _COCKPIT_FAILED=$failed
}

# ─────────────────────────────────────────────────────────────────────────────
# Part 2: Audit Trail Export (Docker)
# ─────────────────────────────────────────────────────────────────────────────
# The Scaleway Audit Trail is an org-level stream of IAM/security events.
# It is not available via Cockpit Exports; it requires a custom OTel Collector
# built with the scwaudittrail receiver from:
#   github.com/scaleway/opentelemetry-collector-scaleway
#
# This section builds and runs that collector inside Docker.

# All Scaleway Instances tagged AUDIT_INSTANCE_TAG in the target zone, as a
# JSON array.  Tolerant of scw failures (e.g. bad creds) — returns "[]" so
# downstream jq pipelines parse cleanly.
_list_audit_instances_json() {
  scw instance server list zone="$SCW_AUDIT_INSTANCE_ZONE" \
    tags.0="$AUDIT_INSTANCE_TAG" -o json 2>/dev/null || echo "[]"
}

# Look up a running Scaleway Instance tagged AUDIT_INSTANCE_TAG.  Echoes
# "<id> <public_ip>" on stdout, or nothing if no match.
_find_audit_instance() {
  _list_audit_instances_json \
    | jq -r '.[] | select(.state == "running") | "\(.id) \(.public_ip.address // "")"' \
    | head -1
}

# True if any Instance tagged AUDIT_INSTANCE_TAG exists in this zone, regardless
# of state.  Broader than _find_audit_instance (which is "running"-only) so the
# end-of-run key cleanup gate also catches stopped/archived collectors whose
# config files still reference an old key.
_has_tagged_audit_instance() {
  [[ "$(_list_audit_instances_json | jq 'length' 2>/dev/null || echo 0)" -gt 0 ]]
}

# Ensure SCW_INSTANCE_IP is set, provisioning a new Instance if it isn't.
# Honors three short-circuit paths before creating anything new:
#   1. SCW_INSTANCE_IP already set — BYO escape hatch for customers who want
#      to reuse an existing Scaleway VM.  The script never tags it, and
#      --teardown leaves it alone.
#   2. An Instance tagged AUDIT_INSTANCE_TAG already exists — idempotent
#      reuse on re-runs of the auto-provisioned default.
#   3. PROVISION_INSTANCE=false — opt out, skip Part 2 entirely.
provision_audit_trail_instance() {
  if [[ -n "${SCW_INSTANCE_IP:-}" ]]; then
    # BYO Instance: conservatively assume it might already host a collector.
    _PRE_EXISTING_AUDIT_INSTANCE=true
    return 0
  fi

  # Opt-out: skip Part 2 entirely.
  if [[ "$PROVISION_INSTANCE" == "false" ]]; then
    warn "SCW_INSTANCE_IP is unset and PROVISION_INSTANCE=false — skipping audit trail"
    return 1
  fi

  # In dry-run, all the live scw queries below (find-existing, ssh-key check,
  # cost lookup) would either fail with fake creds or hit the real API for a
  # read — neither is desirable.  Skip straight to the "would create" output.
  if [[ "$DRY_RUN" == "true" ]]; then
    log "Would provision audit-trail Instance:"
    log "  Type: $SCW_AUDIT_INSTANCE_TYPE   Zone: $SCW_AUDIT_INSTANCE_ZONE   Image: $SCW_AUDIT_INSTANCE_IMAGE"
    log "  Tag:  $AUDIT_INSTANCE_TAG  (idempotent; --teardown removes it)"
    dryrun "Would run: scw instance server create image=$SCW_AUDIT_INSTANCE_IMAGE type=$SCW_AUDIT_INSTANCE_TYPE zone=$SCW_AUDIT_INSTANCE_ZONE ip=dynamic name=$AUDIT_INSTANCE_TAG tags.0=$AUDIT_INSTANCE_TAG -w"
    SCW_INSTANCE_IP="<dry-run-instance-ip>"
    return 0
  fi

  # Mark any tagged Instance (running OR stopped) as pre-existing so end-of-run
  # cleanup doesn't revoke keys a stopped collector's config still references.
  _has_tagged_audit_instance && _PRE_EXISTING_AUDIT_INSTANCE=true

  # Reuse an existing tagged Instance if present.
  local existing id ip
  existing=$(_find_audit_instance)
  if [[ -n "$existing" ]]; then
    id="${existing%% *}"; ip="${existing##* }"
    if [[ -n "$ip" && "$ip" != "null" ]]; then
      log "Reusing existing audit-trail Instance ${id} at ${ip}"
      SCW_INSTANCE_IP="$ip"
      _PRE_EXISTING_AUDIT_INSTANCE=true
      return 0
    fi
    warn "Found existing audit-trail Instance ${id} but it has no public IP — skipping"
    _PRE_EXISTING_AUDIT_INSTANCE=true
    return 1
  fi

  # SSH-key prereq is checked up front in preflight_check_scaleway_ssh_key.

  # Hourly→monthly cost estimate, for the prompt.
  local hourly monthly
  hourly=$(scw instance server-type list zone="$SCW_AUDIT_INSTANCE_ZONE" -o json 2>/dev/null \
    | jq -r --arg t "$SCW_AUDIT_INSTANCE_TYPE" \
        '.[] | select(.name == $t) | (.hourly_price.units + .hourly_price.nanos / 1e9)')
  if [[ -n "$hourly" && "$hourly" != "null" ]]; then
    monthly=$(awk -v h="$hourly" 'BEGIN { printf "%.2f", h * 24 * 30 }')
  else
    hourly="?"; monthly="?"
  fi

  log "Preparing to provision audit-trail Instance:"
  log "  Type: $SCW_AUDIT_INSTANCE_TYPE   Zone: $SCW_AUDIT_INSTANCE_ZONE   Image: $SCW_AUDIT_INSTANCE_IMAGE"
  log "  Cost: €${hourly}/hr  (~€${monthly}/mo)"
  log "  Tag:  $AUDIT_INSTANCE_TAG  (re-runs will reuse this Instance; --teardown removes it)"

  # Prompt unless explicitly approved via PROVISION_INSTANCE=true.
  if [[ "$PROVISION_INSTANCE" != "true" ]]; then
    printf '\033[0;33m[setup]\033[0m  Provision this Instance now? [y/N] ' >&2
    local ans=""
    read -r ans </dev/tty || true
    if [[ ! "$ans" =~ ^[Yy]$ ]]; then
      warn "Skipping audit trail provisioning.  Set SCW_INSTANCE_IP or PROVISION_INSTANCE=true to enable."
      return 1
    fi
  fi

  log "Creating Instance (this takes ~2 min)..."
  local create_resp
  create_resp=$(scw instance server create \
    image="$SCW_AUDIT_INSTANCE_IMAGE" \
    type="$SCW_AUDIT_INSTANCE_TYPE" \
    zone="$SCW_AUDIT_INSTANCE_ZONE" \
    ip=dynamic \
    name="$AUDIT_INSTANCE_TAG" \
    tags.0="$AUDIT_INSTANCE_TAG" \
    -w -o json 2>&1) || { warn "scw instance server create failed: $create_resp"; return 1; }

  local new_id new_ip
  new_id=$(jq -r '.id' <<<"$create_resp")
  new_ip=$(jq -r '.public_ip.address // empty' <<<"$create_resp")
  if [[ -z "$new_ip" ]]; then
    warn "Instance created (id=$new_id) but no public IP was assigned — skipping"
    return 1
  fi

  # Wait for SSH to come up — `-w` returns when the instance state is "running",
  # but cloud-init / sshd may need another 30–120s before accepting connections.
  log "Instance up at ${new_ip} (id=${new_id}) — waiting for SSH..."
  local waited=0
  while (( waited < 180 )); do
    if ssh-keyscan -T 3 "$new_ip" >/dev/null 2>&1; then
      ok "SSH is ready on ${new_ip}"
      SCW_INSTANCE_IP="$new_ip"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done

  warn "SSH did not become reachable on ${new_ip} within 180s — skipping"
  return 1
}

# Delete all Instances tagged AUDIT_INSTANCE_TAG in the target zone, along with
# their volumes and IPs.  Idempotent: prints "nothing to do" if no match.
teardown_audit_trail_instance() {
  log "━━━ Teardown: Audit Trail Instance ━━━"

  local ids
  ids=$(_list_audit_instances_json | jq -r '.[].id')
  if [[ -z "$ids" ]]; then
    log "No Instances tagged '${AUDIT_INSTANCE_TAG}' in ${SCW_AUDIT_INSTANCE_ZONE} — nothing to do."
    return 0
  fi

  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    if [[ "$DRY_RUN" == "true" ]]; then
      dryrun "Would delete Instance ${id} (volumes + IP)"
      continue
    fi
    log "Deleting Instance ${id}..."
    if scw instance server delete "$id" zone="$SCW_AUDIT_INSTANCE_ZONE" \
        with-volumes=all with-ip=true force-shutdown=true >/dev/null 2>&1; then
      ok "Deleted ${id}"
    else
      warn "Failed to delete ${id} — check 'scw instance server get $id'"
    fi
  done <<<"$ids"
}

setup_audit_trail() {
  log "━━━ Part 2: Audit Trail Export ━━━"

  [[ -n "${SCW_ACCESS_KEY:-}"      ]] || { warn "SCW_ACCESS_KEY is required for audit trail — skipping"; return 1; }
  [[ -n "${SCW_ORGANIZATION_ID:-}" ]] || { warn "SCW_ORGANIZATION_ID is required for audit trail — skipping"; return 1; }

  # Auto-provision (or reuse) a Scaleway Instance if SCW_INSTANCE_IP is unset.
  # In dry-run this sets SCW_INSTANCE_IP=<dry-run-instance-ip> and continues.
  provision_audit_trail_instance || return 1

  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "Would build OTel collector and deploy to ${SCW_INSTANCE_IP} via SSH/SCP"
    _AUDIT_DEPLOYED=true
    return 0
  fi

  log "Using SSH user '${SCW_INSTANCE_USER}' for Instance access (override with SCW_INSTANCE_USER)"

  # Create work_dir early — single trap handles both container and dir cleanup
  local work_dir="" cid=""
  work_dir=$(mktemp -d /tmp/scw-audit-trail-XXXXXX) \
    || { warn "Failed to create temp dir — skipping audit trail setup"; return 1; }
  trap '[[ -n "${cid:-}" ]] && docker rm -f "$cid" >/dev/null 2>&1 || true; [[ -n "${work_dir:-}" ]] && rm -rf "$work_dir"' RETURN

  # accept-new is TOFU on first contact (same security as the explicit
  # ssh-keyscan it replaces) but defers to the user's ~/.ssh/config for
  # ProxyJump, so private-subnet customers get bastion handling for free
  # via their existing ssh config without needing script-specific env vars.
  local -a ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=${work_dir}/known_hosts")

  log "Verifying SSH access to ${SCW_INSTANCE_IP}..."
  if ! ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" true 2>/dev/null; then
    warn "Cannot reach ${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP} via SSH."
    warn "Check that:"
    warn "  1. The instance is running and SCW_INSTANCE_IP is correct"
    warn "  2. Your SSH key is registered in Scaleway:"
    warn "     https://www.scaleway.com/en/docs/organizations-and-projects/how-to/create-ssh-key/"
    warn "  3. If the instance is in a private subnet, configure ProxyJump in ~/.ssh/config:"
    warn "     https://www.scaleway.com/en/docs/public-gateways/how-to/use-ssh-bastion/"
    return 1
  fi
  ok "SSH access verified"

  # Locate static files — on disk when running from a clone, downloaded otherwise.
  # AUDIT_TRAIL_REF defaults to main; pin to a commit SHA before GA to prevent
  # a future breaking change (or a push to main) from affecting deployed instances.
  local script_dir audit_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  audit_dir="${script_dir}/audit-trail"

  local _audit_ref="${AUDIT_TRAIL_REF:-main}"
  local _audit_base="https://raw.githubusercontent.com/DataDog/integrations-management/${_audit_ref}/scaleway/log_forwarding/audit-trail"
  local _audit_files=(builder-config.yaml Dockerfile config.yaml opentelemetry-collector.service)

  if [[ -d "$audit_dir" ]]; then
    for f in "${_audit_files[@]}"; do
      cp "${audit_dir}/${f}" "$work_dir/${f}"
    done
  else
    log "audit-trail/ not found locally — downloading from GitHub (ref=${_audit_ref})..."
    for f in "${_audit_files[@]}"; do
      curl -fsSL "${_audit_base}/${f}" -o "$work_dir/${f}" \
        || { warn "Failed to download audit-trail/${f} — skipping"; return 1; }
    done
    ok "Downloaded audit-trail files"
  fi

  # Detect remote CPU architecture to build the correct binary
  local remote_arch goarch
  remote_arch=$(ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" "uname -m")
  case "$remote_arch" in
    x86_64)         goarch="amd64" ;;
    aarch64|arm64)  goarch="arm64" ;;
    *) warn "Unsupported remote architecture: $remote_arch"; return 1 ;;
  esac
  log "Detected remote architecture: $remote_arch (GOARCH=$goarch)"

  log "Building audit trail collector binary for linux/${goarch}..."
  docker build --build-arg "GOARCH=${goarch}" -t scw-audit-trail-builder "$work_dir" \
    || { warn "Docker build failed — skipping audit trail"; return 1; }

  # cid is captured so the RETURN trap removes the container on any failure path.
  cid=$(docker create scw-audit-trail-builder)
  docker cp "$cid:/out/otelcol-audit-trail" "$work_dir/otelcol-audit-trail"
  docker rm "$cid" >/dev/null && cid=""
  ok "Binary built"

  # Deploy to Instance
  log "Deploying to Instance at ${SCW_INSTANCE_IP}..."

  ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" \
    "systemctl stop opentelemetry-collector 2>/dev/null || true; mkdir -p /etc/opentelemetry-collector /usr/local/bin"

  scp "${ssh_opts[@]}" \
    "$work_dir/otelcol-audit-trail" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/usr/local/bin/otelcol-audit-trail"

  scp "${ssh_opts[@]}" \
    "$work_dir/config.yaml" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/etc/opentelemetry-collector/"

  # Restrict the env file to mode 0600 *before* it contains credentials so it
  # is never world-readable on local disk between heredoc and scp.
  (umask 077; cat > "$work_dir/collector.env" <<EOF
SCW_ACCESS_KEY=${SCW_ACCESS_KEY}
SCW_SECRET_KEY=${SCW_SECRET_KEY}
SCW_ORGANIZATION_ID=${SCW_ORGANIZATION_ID}
SCW_REGION=${SCW_REGION}
DD_API_KEY=${DD_API_KEY}
DD_SITE=${DD_SITE}
EOF
  )
  scp "${ssh_opts[@]}" \
    "$work_dir/collector.env" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/etc/opentelemetry-collector/"

  scp "${ssh_opts[@]}" \
    "$work_dir/opentelemetry-collector.service" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/etc/systemd/system/opentelemetry-collector.service"

  ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" \
    "chmod +x /usr/local/bin/otelcol-audit-trail && \
     chmod 600 /etc/opentelemetry-collector/collector.env && \
     systemctl daemon-reload && \
     systemctl enable opentelemetry-collector && \
     systemctl restart opentelemetry-collector"

  ok "Audit trail collector deployed and running on ${SCW_INSTANCE_IP}"
  ok "Verify: ssh ${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP} journalctl -fu opentelemetry-collector"
  ok "Logs will appear in Datadog > Logs within ~1 minute."
  _AUDIT_DEPLOYED=true
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo
  log "Scaleway Cloud Logs → Datadog Setup"
  [[ "$DRY_RUN" == "true" ]] && dryrun "DRY-RUN MODE — no API calls will be made"

  # --teardown is a destructive one-shot: skip the normal setup flow entirely.
  if [[ "$TEARDOWN" == "true" ]]; then
    teardown_audit_trail_instance
    return 0
  fi

  log "DD Site:  $DD_SITE"
  log "Regions:  $SCALEWAY_REGIONS"
  log "Products: $SCALEWAY_PRODUCTS"
  log "Audit trail: $SCW_AUDIT_TRAIL_ENABLED"
  echo

  check_prereqs
  echo

  # Fail fast on Datadog auth/permission issues so we don't leave half-built
  # Scaleway resources behind if the final Part 3 registration would 403.
  preflight_check_datadog_access

  # If audit trail will actually try to provision, verify SSH key prereq up
  # front so we don't get half-built before discovering the missing key.
  if [[ "$SCW_AUDIT_TRAIL_ENABLED" == "true" \
        && -z "${SCW_INSTANCE_IP:-}" \
        && "$PROVISION_INSTANCE" != "false" ]]; then
    preflight_check_scaleway_ssh_key
  fi
  echo

  if [[ "$SKIP_IAM" == "true" ]]; then
    log "Skipping IAM provisioning (SKIP_IAM=true) — using provided credentials."
    IAM_ACCESS_KEY="$SCW_ACCESS_KEY"
    IAM_SECRET_KEY="$SCW_SECRET_KEY"
  else
    provision_iam_application
  fi

  setup_cockpit_exports
  echo

  if [[ "$SCW_AUDIT_TRAIL_ENABLED" == "true" ]]; then
    setup_audit_trail || true
    echo
  fi

  # Skip Datadog account registration if nothing actually got set up.
  # "Nothing" means: Cockpit had failures and produced no working exporters,
  # AND the audit trail didn't deploy.  An empty Scaleway project with zero
  # Cockpit failures still registers, so future exports flow once products
  # are created.
  local cockpit_working=$(( _COCKPIT_CREATED + _COCKPIT_SKIPPED ))
  if (( cockpit_working == 0 )) && (( _COCKPIT_FAILED > 0 )) && [[ "$_AUDIT_DEPLOYED" != "true" ]]; then
    warn "Skipping Datadog account registration: $_COCKPIT_FAILED Cockpit export(s) failed and audit trail did not deploy."
    warn "  Nothing is forwarding logs, so we won't create a dangling account entry."
    warn "  Fix the failures above and re-run to register the integration."
    return 0
  fi

  register_datadog_account

  # A deployed audit collector that was not redeployed this run still holds the
  # old key, so revoking it would break log forwarding.  But if no prior
  # collector exists at all (auto-provision path on first/failed attempts),
  # there's nothing to break — clean up the staged old keys so they don't
  # accumulate across runs.
  if [[ "$SCW_AUDIT_TRAIL_ENABLED" != "true" ]] \
     || [[ "$_AUDIT_DEPLOYED" == "true" ]] \
     || [[ "$_PRE_EXISTING_AUDIT_INSTANCE" != "true" ]]; then
    # Run the delete with the original (owner-level) creds — the script's
    # current SCW_*_KEY are the app's, which lack IAM write.  Use env-var
    # form so the child `scw` process actually inherits the override.
    local old_key
    while IFS= read -r old_key; do
      [[ -z "$old_key" ]] && continue
      if SCW_ACCESS_KEY="$_ORIG_SCW_ACCESS_KEY" SCW_SECRET_KEY="$_ORIG_SCW_SECRET_KEY" \
           scw iam api-key delete "${old_key}" 2>/dev/null; then
        log "Deleted old API key ${old_key}"
      else
        warn "Could not delete old API key ${old_key} — remove it manually from the Scaleway console"
      fi
    done <<< "$_IAM_OLD_KEYS"
  else
    local stale_keys
    stale_keys=$(tr '\n' ' ' <<< "$_IAM_OLD_KEYS" | tr -s ' ')
    stale_keys="${stale_keys# }"; stale_keys="${stale_keys% }"
    [[ -n "$stale_keys" ]] && warn "Audit collector was not redeployed this run — skipping cleanup of old IAM keys. Rotate manually when safe: ${stale_keys}"
  fi

  ok "Setup complete."
  print_datadog_credentials
}

main "$@"
