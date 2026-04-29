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
#   scw CLI            must be installed and configured before running this
#                       script ('scw init'). Credentials must have IAM Manager
#                       or Org Owner permissions (used only for Step 0).
#   curl, jq           (required for Part 1)
#   Docker, ssh, scp   (required for Part 2)
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
#
#   SCW_PROJECT_ID        Scaleway project ID to set up exports for    [default: from scw config]
#                         Only set this to target a non-default project.
#   SCALEWAY_REGIONS      Comma-separated Cockpit regions              [default: fr-par,nl-ams,pl-waw]
#   SCALEWAY_PRODUCTS     Comma-separated Scaleway products to export  [default: all]
#                         Use "all" to export every Cockpit-integrated product.
#                         Example: "kubernetes,rdb,object-storage"
#   ENABLE_AUDIT_TRAIL    Set up the audit trail collector             [default: true]
#   SCW_INSTANCE_IP       IP of the Scaleway Instance for audit trail  [required for Part 2]
#   SCW_INSTANCE_USER     SSH user for the Instance                    [default: root]
#   SCW_ACCOUNT_NAME      Name for the Datadog integration account     [default: SCW_PROJECT_ID]
#
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# printf '%(%H:%M:%S)T' requires bash 4.2+; macOS ships bash 3.2 by default.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]] || { [[ "${BASH_VERSINFO[0]}" -eq 4 ]] && [[ "${BASH_VERSINFO[1]}" -lt 2 ]]; }; then
  printf 'bash 4.2 or later is required (you have %s).\n' "$BASH_VERSION" >&2
  printf 'Install it with: brew install bash\n' >&2
  exit 1
fi

# ── Flags ─────────────────────────────────────────────────────────────────────
DRY_RUN=false
for _arg in "$@"; do [[ "$_arg" == "--dry-run" ]] && DRY_RUN=true; done
unset _arg

# ── Scaleway credentials — read from scw config, overridable via env ──────────
scw_config_get() { scw config get "$1" 2>/dev/null || true; }

SCW_SECRET_KEY="${SCW_SECRET_KEY:-$(scw_config_get secret-key)}"
SCW_ACCESS_KEY="${SCW_ACCESS_KEY:-$(scw_config_get access-key)}"
SCW_ORGANIZATION_ID="${SCW_ORGANIZATION_ID:-$(scw_config_get default-organization-id)}"

if [[ -z "${SCW_SECRET_KEY:-}" ]]; then
  if ! command -v scw &>/dev/null; then
    printf '\033[0;31m[error]\033[0m  scw CLI not found.\n' >&2
    printf '  Install it first:\n' >&2
    printf '    macOS:  brew install scw\n' >&2
    printf '    Linux:  https://www.scaleway.com/en/docs/developer-tools/scaleway-cli/reference-content/install-cli/\n' >&2
    printf '  Then run: scw init\n' >&2
    exit 1
  fi
  printf '\033[0;31m[error]\033[0m  Scaleway credentials not found.\n' >&2
  printf '  Run '\''scw init'\'' to configure the CLI, then re-run this script.\n' >&2
  exit 1
fi

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
  scw cockpit data-source list --help 2>&1 \
    | grep 'region=' \
    | sed 's/.*(\(.*\))/\1/' \
    | tr '|' '\n' | tr -d ' ' \
    | grep -Ev '^$|^all$' \
    | paste -sd ',' \
    || echo "fr-par,nl-ams,pl-waw"
}
SCALEWAY_REGIONS="${SCALEWAY_REGIONS:-$(_scw_cockpit_regions)}"
SCALEWAY_PRODUCTS="${SCALEWAY_PRODUCTS:-all}"            # "all" or CSV of Cockpit product names (e.g. "kubernetes,rdb")
ENABLE_AUDIT_TRAIL="${ENABLE_AUDIT_TRAIL:-true}"
SCW_REGION="${SCW_REGION:-$(scw_config_get default-region)}"
SCW_REGION="${SCW_REGION:-fr-par}"        # fallback if not configured
SCW_INSTANCE_IP="${SCW_INSTANCE_IP:-}"       # IP of the Scaleway Instance for audit trail
SCW_INSTANCE_USER="${SCW_INSTANCE_USER:-root}" # SSH user for the Instance (default: root)
SCW_ACCOUNT_NAME="${SCW_ACCOUNT_NAME:-}" # defaults to SCW_PROJECT_ID at registration time

SCW_API="https://api.scaleway.com"
EXPORTER_NAME="${EXPORTER_NAME:-datadog-logs-${DD_SITE}}" # one exporter per Datadog datacenter
IAM_APP_NAME="datadog-integration"                      # stable IAM application name
IAM_POLICY_NAME="datadog-integration-policy"            # stable IAM policy name
IAM_ACCESS_KEY=""   # set by provision_iam_application
IAM_SECRET_KEY=""   # set by provision_iam_application
_IAM_OLD_KEYS=""    # old keys staged for cleanup after account registration
# Internal: skip IAM provisioning when credentials are supplied externally (multi-site testing).
SKIP_IAM="${SKIP_IAM:-false}"
# Internal: if set, write generated IAM credentials to this file for multi-site reuse.
MULTISITE_CREDS_FILE="${MULTISITE_CREDS_FILE:-}"

# ── Logging helpers ───────────────────────────────────────────────────────────
_ts()    { printf '%(%H:%M:%S)T' -1; }
log()    { printf '\033[0;34m[%s]\033[0m  %s\n'    "$(_ts)" "$*"; }
ok()     { printf '\033[0;32m[%s] ✓\033[0m  %s\n' "$(_ts)" "$*"; }
warn()   { printf '\033[0;33m[%s] ⚠\033[0m  %s\n' "$(_ts)" "$*" >&2; }
die()    { printf '\033[0;31m[%s] ✗\033[0m  %s\n' "$(_ts)" "$*" >&2; exit 1; }
dryrun() { printf '\033[0;35m[%s] ~\033[0m  %s\n' "$(_ts)" "$*" >&2; }

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
  local args=(-sS -w $'\n%{http_code}' -H "X-Auth-Token: $SCW_SECRET_KEY")
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
  local args=(-sS -w $'\n%{http_code}'
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

# ── Prerequisites check ───────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  command -v curl &>/dev/null || missing+=(curl)
  command -v jq   &>/dev/null || missing+=(jq)
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required tools: ${missing[*]}
  Install with:
    macOS:   brew install ${missing[*]}
    Linux:   apt-get install -y ${missing[*]}   (or your distro's equivalent)
  Then re-run this script."
  fi

  if [[ "$ENABLE_AUDIT_TRAIL" == "true" ]]; then
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
      warn "  Set ENABLE_AUDIT_TRAIL=false to skip Part 2 and suppress this warning."
      ENABLE_AUDIT_TRAIL="false"
    fi
  fi

  log "Prerequisites OK"
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

  local policy_body
  policy_body=$(jq -n \
    --arg name       "$IAM_POLICY_NAME" \
    --arg org        "$SCW_ORGANIZATION_ID" \
    --arg app_id     "$app_id" \
    --arg project_id "$SCW_PROJECT_ID" \
    '{
      name:            $name,
      organization_id: $org,
      application_id:  $app_id,
      rules: [
        {
          permission_set_names: ["ObservabilityFullAccess", "AllProductsReadOnly"],
          project_ids:          [$project_id]
        },
        {
          permission_set_names: ["AuditTrailReadOnly"],
          organization_id:      $org
        }
      ]
    }')

  local policy_resp
  if [[ -n "$policy_id" ]]; then
    log "Updating IAM policy '${IAM_POLICY_NAME}' (id=${policy_id})..."
    policy_resp=$(scw_request PATCH "/iam/v1alpha1/policies/${policy_id}" "$policy_body") \
      || die "Failed to update IAM policy — fix the error above and re-run the script"
    ok "Updated IAM policy '${IAM_POLICY_NAME}' (id=${policy_id})"
  else
    log "Creating IAM policy '${IAM_POLICY_NAME}'..."
    policy_resp=$(scw_post "/iam/v1alpha1/policies" "$policy_body") \
      || die "Failed to create IAM policy — fix the error above and re-run the script"
    policy_id=$(jq -r '.id' <<< "$policy_resp")
    ok "Created IAM policy '${IAM_POLICY_NAME}' (id=${policy_id})"
  fi

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
    printf 'SCW_ACCESS_KEY=%s\nSCW_SECRET_KEY=%s\n' "$IAM_ACCESS_KEY" "$IAM_SECRET_KEY" > "$MULTISITE_CREDS_FILE"
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
  accounts_resp=$(dd_get "/api/v2/web-integrations/scaleway/accounts") \
    || die "Failed to list Datadog Scaleway accounts"
  account_id=$(jq -r --arg name "$account_name" \
    'first(.data[] | select(.attributes.name == $name) | .id) // empty' <<< "$accounts_resp")

  local action_resp
  if [[ -n "$account_id" ]]; then
    log "Account exists — updating (id=${account_id})..."
    action_resp=$(dd_patch "/api/v2/web-integrations/scaleway/accounts/${account_id}" "$payload") \
      || die "Failed to update Datadog Scaleway account"
    account_id=$(jq -r '.data.id // .id // "dry-run-id"' <<< "$action_resp")
    ok "Updated Datadog Scaleway account '${account_name}' (id=${account_id})"
  else
    log "Creating Datadog Scaleway account '${account_name}'..."
    action_resp=$(dd_post "/api/v2/web-integrations/scaleway/accounts" "$payload") \
      || die "Failed to create Datadog Scaleway account"
    account_id=$(jq -r '.data.id // .id // "dry-run-id"' <<< "$action_resp")
    ok "Created Datadog Scaleway account '${account_name}' (id=${account_id})"
  fi

  echo
  ok "Integration is now active  account=${account_name}  id=${account_id}"
  echo
}

# ─────────────────────────────────────────────────────────────────────────────
# Part 1: Cockpit Native Data Exports
# ─────────────────────────────────────────────────────────────────────────────

# Lists the IDs of Scaleway-managed log data sources for a project in a region.
# Scaleway creates these automatically for each project where Cockpit products
# are active; we look for origin=scaleway to skip user-created custom sources.
get_log_datasource_ids() {
  local project_id="$1" region="$2"
  scw_get "/cockpit/v1/regions/${region}/data-sources?project_id=${project_id}&origin=scaleway&types=logs&page_size=100" \
    | jq -r '.data_sources[].id // empty'
}

# Returns true if an exporter named $EXPORTER_NAME already exists for the data source.
exporter_exists() {
  local datasource_id="$1" region="$2" project_id="$3"
  local resp count
  resp=$(scw_get "/cockpit/v1/regions/${region}/exporters?project_id=${project_id}&datasource_id=${datasource_id}&page_size=100") || return 1
  count=$(jq --arg name "$EXPORTER_NAME" '[.exporters[] | select(.name == $name)] | length' <<< "$resp" 2>/dev/null) || return 1
  (( count > 0 ))
}

create_exporter() {
  local datasource_id="$1" region="$2" project_id="$3"

  # Build the products JSON array: ["all"] or a proper array from the CSV
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

    for ds_id in "${datasource_ids[@]}"; do
      if exporter_exists "$ds_id" "$region" "$SCW_PROJECT_ID" 2>/dev/null; then
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

setup_audit_trail() {
  log "━━━ Part 2: Audit Trail Export ━━━"

  [[ -n "${SCW_ACCESS_KEY:-}"      ]] || { warn "SCW_ACCESS_KEY is required for audit trail — skipping"; return 1; }
  [[ -n "${SCW_ORGANIZATION_ID:-}" ]] || { warn "SCW_ORGANIZATION_ID is required for audit trail — skipping"; return 1; }

  # Instance IP — list available instances if not provided
  if [[ -z "${SCW_INSTANCE_IP:-}" ]]; then
    warn "SCW_INSTANCE_IP is not set. Your available instances:"
    scw instance server list 2>/dev/null || true
    warn "Set SCW_INSTANCE_IP to the public IP of the instance to deploy the audit trail collector — skipping"
    return 1
  fi

  log "Using SSH user '${SCW_INSTANCE_USER}' for Instance access (override with SCW_INSTANCE_USER)"

  # Create work_dir early — single trap handles both container and dir cleanup
  local work_dir="" cid=""
  work_dir=$(mktemp -d /tmp/scw-audit-trail-XXXXXX) \
    || { warn "Failed to create temp dir — skipping audit trail setup"; return 1; }
  trap '[[ -n "${cid:-}" ]] && docker rm -f "$cid" >/dev/null 2>&1 || true; [[ -n "${work_dir:-}" ]] && rm -rf "$work_dir"' RETURN

  # Fetch and pin the instance's host key so we never skip verification.
  # StrictHostKeyChecking=no would open a MITM window on a script that deploys
  # credentials to root — we accept the key once here instead.
  log "Fetching SSH host key from ${SCW_INSTANCE_IP}..."
  ssh-keyscan -T 10 "$SCW_INSTANCE_IP" > "$work_dir/known_hosts" 2>/dev/null \
    || {
      warn "Could not reach ${SCW_INSTANCE_IP} on port 22 — skipping audit trail."
      warn "  Check that:"
      warn "    1. The instance is running and SCW_INSTANCE_IP is correct"
      warn "    2. Port 22 is open in the instance's security group"
      warn "    3. Your SSH key is registered in Scaleway:"
      warn "       https://www.scaleway.com/en/docs/organizations-and-projects/how-to/create-ssh-key/"
      return 1
    }

  local -a ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o "UserKnownHostsFile=${work_dir}/known_hosts")

  log "Verifying SSH access to ${SCW_INSTANCE_IP}..."
  if ! ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" true 2>/dev/null; then
    warn "Cannot reach ${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP} via SSH."
    warn "Make sure your public SSH key is registered in your Scaleway account and re-run:"
    warn "  https://www.scaleway.com/en/docs/organizations-and-projects/how-to/create-ssh-key/"
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
  docker build --no-cache --build-arg "GOARCH=${goarch}" -t scw-audit-trail-builder "$work_dir" \
    || { warn "Docker build failed — skipping audit trail"; return 1; }

  # Extract binary from image; cid is set so the trap cleans it up on any failure
  cid=$(docker create scw-audit-trail-builder)
  docker cp "$cid:/out/otelcol-audit-trail" "$work_dir/otelcol-audit-trail"
  docker rm "$cid" >/dev/null && cid=""
  ok "Binary built"

  # Deploy to Instance
  log "Deploying to Instance at ${SCW_INSTANCE_IP}..."

  ssh "${ssh_opts[@]}" "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}" \
    "systemctl stop opentelemetry-collector 2>/dev/null || true && mkdir -p /etc/opentelemetry-collector /usr/local/bin"

  scp "${ssh_opts[@]}" \
    "$work_dir/otelcol-audit-trail" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/usr/local/bin/otelcol-audit-trail"

  scp "${ssh_opts[@]}" \
    "$work_dir/config.yaml" \
    "${SCW_INSTANCE_USER}@${SCW_INSTANCE_IP}:/etc/opentelemetry-collector/"

  cat > "$work_dir/collector.env" <<EOF
SCW_ACCESS_KEY=${SCW_ACCESS_KEY}
SCW_SECRET_KEY=${SCW_SECRET_KEY}
SCW_ORGANIZATION_ID=${SCW_ORGANIZATION_ID}
SCW_REGION=${SCW_REGION}
DD_API_KEY=${DD_API_KEY}
DD_SITE=${DD_SITE}
EOF
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
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo
  log "Scaleway Cloud Logs → Datadog Setup"
  [[ "$DRY_RUN" == "true" ]] && dryrun "DRY-RUN MODE — no API calls will be made"
  log "DD Site:  $DD_SITE"
  log "Regions:  $SCALEWAY_REGIONS"
  log "Products: $SCALEWAY_PRODUCTS"
  log "Audit trail: $ENABLE_AUDIT_TRAIL"
  echo

  check_prereqs
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

  if [[ "$ENABLE_AUDIT_TRAIL" == "true" ]]; then
    setup_audit_trail || true
    echo
  fi

  register_datadog_account

  # Clean up old IAM keys now that the new key is persisted in Datadog.
  local old_key
  while IFS= read -r old_key; do
    [[ -z "$old_key" ]] && continue
    scw iam api-key delete "access-key=${old_key}" 2>/dev/null \
      && log "Deleted old API key ${old_key}" \
      || warn "Could not delete old API key ${old_key} — remove it manually from the Scaleway console"
  done <<< "$_IAM_OLD_KEYS"

  ok "Setup complete."
  print_datadog_credentials
}

main "$@"
