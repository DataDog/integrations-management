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
#             Runs an OpenTelemetry Collector with the scwaudittrail receiver
#             to forward IAM/org-level audit events to Datadog Logs.
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
#   Docker             (required for Part 2)
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
#                SCW_SECRET_KEY=x SCW_ACCESS_KEY=x SCW_ORGANIZATION_ID=x \
#                SCW_PROJECT_ID=x DD_API_KEY=x DD_APP_KEY=x \
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
#   SCW_ORGANIZATION_ID   Scaleway organization ID [default: from scw config, required for audit trail]
#
#   SCW_PROJECT_ID        Scaleway project ID to set up exports for    [required for Part 1]
#   SCALEWAY_REGIONS      Comma-separated Cockpit regions              [default: fr-par,nl-ams,pl-waw]
#   SCALEWAY_PRODUCTS     Comma-separated Scaleway products to export  [default: all]
#                         Use "all" to export every Cockpit-integrated product.
#                         Example: "kubernetes,rdb,object-storage"
#   ENABLE_AUDIT_TRAIL    Set up the audit trail collector             [default: true]
#   SCW_ACCOUNT_NAME      Name for the Datadog integration account     [default: SCW_PROJECT_ID]
#
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Flags ─────────────────────────────────────────────────────────────────────
DRY_RUN=false
for _arg in "$@"; do [[ "$_arg" == "--dry-run" ]] && DRY_RUN=true; done
unset _arg

# ── Scaleway credentials — read from scw config, overridable via env ──────────
scw_config_get() { scw config get "$1" 2>/dev/null || true; }

SCW_SECRET_KEY="${SCW_SECRET_KEY:-$(scw_config_get secret-key)}"
SCW_ACCESS_KEY="${SCW_ACCESS_KEY:-$(scw_config_get access-key)}"
SCW_ORGANIZATION_ID="${SCW_ORGANIZATION_ID:-$(scw_config_get default-organization-id)}"

: "${SCW_SECRET_KEY:?SCW_SECRET_KEY not found. Run 'scw init' or set SCW_SECRET_KEY.}"

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
SCALEWAY_PRODUCTS="${SCALEWAY_PRODUCTS:-all}"            # "all" or CSV of product names
ENABLE_AUDIT_TRAIL="${ENABLE_AUDIT_TRAIL:-true}"
SCW_REGION="${SCW_REGION:-$(scw_config_get default-region)}"
SCW_REGION="${SCW_REGION:-fr-par}"        # fallback if not configured
SCW_INSTANCE_IP="${SCW_INSTANCE_IP:-}"    # IP of the Scaleway Instance for audit trail
SCW_ACCOUNT_NAME="${SCW_ACCOUNT_NAME:-}" # defaults to SCW_PROJECT_ID at registration time

SCW_API="https://api.scaleway.com"
EXPORTER_NAME="datadog-logs-dd-setup"                   # stable name for idempotency
IAM_APP_NAME="datadog-integration"                      # stable IAM application name
IAM_POLICY_NAME="datadog-integration-policy"            # stable IAM policy name
IAM_ACCESS_KEY=""   # set by provision_iam_application
IAM_SECRET_KEY=""   # set by provision_iam_application

# ── Logging helpers ───────────────────────────────────────────────────────────
_ts()    { date -u +%H:%M:%S; }
log()    { printf '\033[0;34m[%s]\033[0m  %s\n'    "$(_ts)" "$*"; }
ok()     { printf '\033[0;32m[%s] ✓\033[0m  %s\n' "$(_ts)" "$*"; }
warn()   { printf '\033[0;33m[%s] ⚠\033[0m  %s\n' "$(_ts)" "$*" >&2; }
die()    { printf '\033[0;31m[%s] ✗\033[0m  %s\n' "$(_ts)" "$*" >&2; exit 1; }
dryrun() { printf '\033[0;35m[%s] ~\033[0m  %s\n' "$(_ts)" "$*" >&2; }

# Stub JSON returned by all API helpers in dry-run mode.  Contains enough
# fields to satisfy every jq query in this script; empty arrays mean "nothing
# found" so create-or-update paths always take the create branch.
_DRY_RUN_STUB='{"id":"dry-run-id","access_key":"DRY_RUN_ACCESS_KEY","secret_key":"DRY_RUN_SECRET_KEY","status":"active","applications":[],"policies":[],"data_sources":[],"exporters":[],"data":[]}'

# ── Scaleway API helpers ──────────────────────────────────────────────────────
scw_get() {
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "GET  ${SCW_API}${1}"
    echo "$_DRY_RUN_STUB"; return
  fi
  curl -fsSL \
    -H "X-Auth-Token: $SCW_SECRET_KEY" \
    "${SCW_API}${1}"
}

scw_post() {
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "POST ${SCW_API}${1}"
    dryrun "body ${2}"
    echo "$_DRY_RUN_STUB"; return
  fi
  local body http_code resp
  resp=$(curl -sS -X POST \
    -H "X-Auth-Token: $SCW_SECRET_KEY" \
    -H "Content-Type: application/json" \
    -d "$2" \
    -w '\n%{http_code}' \
    "${SCW_API}${1}")
  http_code=$(tail -n1 <<< "$resp")
  body=$(sed '$d' <<< "$resp")
  if [[ "$http_code" -ge 400 ]]; then
    echo "$body" >&2
    return 1
  fi
  echo "$body"
}

# ── Datadog endpoint ──────────────────────────────────────────────────────────
# Maps DD_SITE to the Datadog logs intake HTTP endpoint.
dd_logs_endpoint() {
  echo "https://http-intake.logs.${DD_SITE}"
}

# ── Datadog API helpers ───────────────────────────────────────────────────────
dd_get() {
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "GET  https://api.${DD_SITE}${1}"
    echo "$_DRY_RUN_STUB"; return
  fi
  local http_code resp body
  resp=$(curl -sS \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    -w '\n%{http_code}' \
    "https://api.${DD_SITE}${1}")
  http_code=$(tail -n1 <<< "$resp")
  body=$(sed '$d' <<< "$resp")
  if [[ "$http_code" -ge 400 ]]; then
    echo "$body" >&2
    return 1
  fi
  echo "$body"
}

dd_post() {
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "POST https://api.${DD_SITE}${1}"
    dryrun "body ${2}"
    echo "$_DRY_RUN_STUB"; return
  fi
  local http_code resp body
  resp=$(curl -sS -X POST \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    -H "Content-Type: application/json" \
    -d "$2" \
    -w '\n%{http_code}' \
    "https://api.${DD_SITE}${1}")
  http_code=$(tail -n1 <<< "$resp")
  body=$(sed '$d' <<< "$resp")
  if [[ "$http_code" -ge 400 ]]; then
    echo "$body" >&2
    return 1
  fi
  echo "$body"
}

dd_patch() {
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "PATCH https://api.${DD_SITE}${1}"
    dryrun "body  ${2}"
    echo "$_DRY_RUN_STUB"; return
  fi
  local http_code resp body
  resp=$(curl -sS -X PATCH \
    -H "DD-API-KEY: $DD_API_KEY" \
    -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    -H "Content-Type: application/json" \
    -d "$2" \
    -w '\n%{http_code}' \
    "https://api.${DD_SITE}${1}")
  http_code=$(tail -n1 <<< "$resp")
  body=$(sed '$d' <<< "$resp")
  if [[ "$http_code" -ge 400 ]]; then
    echo "$body" >&2
    return 1
  fi
  echo "$body"
}

# ── Prerequisites check ───────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  command -v curl &>/dev/null || missing+=(curl)
  command -v jq   &>/dev/null || missing+=(jq)
  [[ ${#missing[@]} -eq 0 ]] || die "Missing required tools: ${missing[*]}"
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
  : "${SCW_PROJECT_ID:?SCW_PROJECT_ID is required. Set it to your Scaleway project ID.}"

  # ── Find or create the IAM application ──────────────────────────────────────
  log "Checking for existing IAM application '${IAM_APP_NAME}'..."
  local apps_resp app_id
  apps_resp=$(scw_get "/iam/v1alpha1/applications?organization_id=${SCW_ORGANIZATION_ID}&name=${IAM_APP_NAME}&page_size=100") \
    || die "Failed to list IAM applications"
  app_id=$(jq -r --arg name "$IAM_APP_NAME" \
    '.applications[] | select(.name == $name) | .id' <<< "$apps_resp" | head -n1)

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

  # ── Find or create the IAM policy ─────────────────────────────────────────
  log "Checking for existing IAM policy '${IAM_POLICY_NAME}'..."
  local policies_resp policy_id
  policies_resp=$(scw_get "/iam/v1alpha1/policies?organization_id=${SCW_ORGANIZATION_ID}&application_id=${app_id}&page_size=100") \
    || die "Failed to list IAM policies"
  policy_id=$(jq -r --arg name "$IAM_POLICY_NAME" --arg app_id "$app_id" \
    '.policies[] | select(.name == $name and .application_id == $app_id) | .id' <<< "$policies_resp" | head -n1)

  if [[ -n "$policy_id" ]]; then
    ok "IAM policy '${IAM_POLICY_NAME}' already exists (id=${policy_id})"
  else
    log "Creating IAM policy '${IAM_POLICY_NAME}'..."
    local policy_body policy_resp
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
            permission_set_names: ["ObservabilityFullAccess"],
            project_ids:          [$project_id]
          }
        ]
      }')
    policy_resp=$(scw_post "/iam/v1alpha1/policies" "$policy_body") \
      || die "Failed to create IAM policy"
    policy_id=$(jq -r '.id' <<< "$policy_resp")
    ok "Created IAM policy '${IAM_POLICY_NAME}' (id=${policy_id})"
  fi

  # ── Generate a new API key for the application ────────────────────────────
  log "Generating API key for application '${IAM_APP_NAME}'..."
  local key_body key_resp
  key_body=$(jq -n \
    --arg app_id "$app_id" \
    '{"application_id": $app_id, "description": "Datadog integration setup"}')
  key_resp=$(scw_post "/iam/v1alpha1/api-keys" "$key_body") \
    || die "Failed to create API key"
  IAM_ACCESS_KEY=$(jq -r '.access_key' <<< "$key_resp")
  IAM_SECRET_KEY=$(jq -r '.secret_key'  <<< "$key_resp")
  ok "Generated API key (access_key=${IAM_ACCESS_KEY})"

  # ── Switch to application credentials for all subsequent calls ───────────
  SCW_ACCESS_KEY="$IAM_ACCESS_KEY"
  SCW_SECRET_KEY="$IAM_SECRET_KEY"
  log "Switched to application credentials for remaining setup."
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

  # Check for an existing account with this name
  log "Checking for existing Datadog Scaleway account '${account_name}'..."
  local accounts_resp account_id
  accounts_resp=$(dd_get "/api/v2/web-integrations/scaleway/accounts") \
    || die "Failed to list Datadog Scaleway accounts"
  account_id=$(jq -r --arg name "$account_name" \
    '.data[] | select(.name == $name) | .id' <<< "$accounts_resp" | head -n1)

  local action_resp
  if [[ -n "$account_id" ]]; then
    log "Account exists — updating (id=${account_id})..."
    action_resp=$(dd_patch "/api/v2/web-integrations/scaleway/accounts/${account_id}" "$payload") \
      || die "Failed to update Datadog Scaleway account"
    account_id=$(jq -r '.data.id // "dry-run-id"' <<< "$action_resp")
    ok "Updated Datadog Scaleway account '${account_name}' (id=${account_id})"
  else
    log "Creating Datadog Scaleway account '${account_name}'..."
    action_resp=$(dd_post "/api/v2/web-integrations/scaleway/accounts" "$payload") \
      || die "Failed to create Datadog Scaleway account"
    account_id=$(jq -r '.data.id // "dry-run-id"' <<< "$action_resp")
    ok "Created Datadog Scaleway account '${account_name}' (id=${account_id})"
  fi

  echo
  ok "Integration is now active  account=${account_name}  id=${account_id}"
  echo
}

# ─────────────────────────────────────────────────────────────────────────────
# Part 1: Cockpit Native Data Exports
# ─────────────────────────────────────────────────────────────────────────────

get_project_id() {
  [[ -n "$SCW_PROJECT_ID" ]] || die "SCW_PROJECT_ID is required. Set it to your Scaleway project ID."
  echo "$SCW_PROJECT_ID"
}

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
    products_json=$(jq -Rcs 'split(",") | map(ltrimstr(" ") | rtrimstr(" "))' <<< "$SCALEWAY_PRODUCTS")
  fi

  local body
  body=$(jq -n \
    --arg  name     "$EXPORTER_NAME" \
    --arg  ds_id    "$datasource_id" \
    --arg  api_key  "$DD_API_KEY" \
    --arg  endpoint "$(dd_logs_endpoint)" \
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

  local project
  project=$(get_project_id)

  IFS=',' read -ra regions <<< "$SCALEWAY_REGIONS"

  log "Project: $project | Regions: ${regions[*]} | Products: $SCALEWAY_PRODUCTS"
  echo

  local created=0 skipped=0 failed=0

  for region in "${regions[@]}"; do
    local datasource_ids
    mapfile -t datasource_ids < <(get_log_datasource_ids "$project" "$region" 2>/dev/null || true)

    if [[ ${#datasource_ids[@]} -eq 0 ]]; then
      warn "No Scaleway log data sources found  project=$project  region=$region — skipping"
      ((skipped++)) || true
      continue
    fi

    for ds_id in "${datasource_ids[@]}"; do
      if exporter_exists "$ds_id" "$region" "$project" 2>/dev/null; then
        ok "Already exported  project=$project  region=$region  datasource=$ds_id"
        ((skipped++)) || true
      elif create_exporter "$ds_id" "$region" "$project"; then
        ((created++)) || true
      else
        ((failed++)) || true
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

  [[ -n "${SCW_ACCESS_KEY:-}"    ]] || { warn "SCW_ACCESS_KEY is required for audit trail — skipping"; return 1; }
  [[ -n "${SCW_ORGANIZATION_ID:-}" ]] || { warn "SCW_ORGANIZATION_ID is required for audit trail — skipping"; return 1; }
  [[ -n "${SCW_INSTANCE_IP:-}"   ]] || { warn "SCW_INSTANCE_IP is required for audit trail — skipping"; return 1; }

  local missing=()
  command -v docker &>/dev/null || missing+=(docker)
  command -v ssh    &>/dev/null || missing+=(ssh)
  command -v scp    &>/dev/null || missing+=(scp)
  [[ ${#missing[@]} -eq 0 ]] || { warn "Missing required tools for audit trail: ${missing[*]} — skipping"; return 1; }

  # Locate static files relative to this script
  local script_dir audit_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  audit_dir="${script_dir}/audit-trail"
  [[ -d "$audit_dir" ]] || { warn "audit-trail/ directory not found at ${audit_dir} — skipping"; return 1; }

  local work_dir
  work_dir=$(mktemp -d /tmp/scw-audit-trail-XXXXXX)
  # Always clean up temp dir containing credentials, even on failure
  trap 'rm -rf "${work_dir:?}"' RETURN

  # Detect remote CPU architecture to build the correct binary
  local ssh_opts="-o StrictHostKeyChecking=no -o BatchMode=yes"
  local remote_arch goarch
  # shellcheck disable=SC2086
  remote_arch=$(ssh $ssh_opts "root@${SCW_INSTANCE_IP}" "uname -m") \
    || { warn "Could not connect to Instance at ${SCW_INSTANCE_IP}"; return 1; }
  case "$remote_arch" in
    x86_64)         goarch="amd64" ;;
    aarch64|arm64)  goarch="arm64" ;;
    *) warn "Unsupported remote architecture: $remote_arch"; return 1 ;;
  esac
  log "Detected remote architecture: $remote_arch (GOARCH=$goarch)"

  # builder-config.yaml — defines the custom OTel collector to compile
  # Copy static build files into temp dir
  cp "${audit_dir}/builder-config.yaml" "$work_dir/builder-config.yaml"
  cp "${audit_dir}/Dockerfile"          "$work_dir/Dockerfile"
  cp "${audit_dir}/config.yaml"         "$work_dir/config.yaml"
  cp "${audit_dir}/opentelemetry-collector.service" "$work_dir/opentelemetry-collector.service"

  log "Building audit trail collector binary for linux/${goarch}..."
  docker build --no-cache --build-arg "GOARCH=${goarch}" -t scw-audit-trail-builder "$work_dir" \
    || { warn "Docker build failed — skipping audit trail"; return 1; }

  # Extract binary from image; extend trap to remove container on any failure
  local cid
  cid=$(docker create scw-audit-trail-builder)
  trap 'docker rm -f "$cid" >/dev/null 2>&1 || true; rm -rf "${work_dir:?}"' RETURN
  docker cp "$cid:/out/otelcol-audit-trail" "$work_dir/otelcol-audit-trail"
  docker rm "$cid" >/dev/null
  ok "Binary built"

  # Credentials env file — written at deploy time, chmod 600 on Instance
  cat > "$work_dir/collector.env" <<EOF
SCW_ACCESS_KEY=${SCW_ACCESS_KEY}
SCW_SECRET_KEY=${SCW_SECRET_KEY}
SCW_ORGANIZATION_ID=${SCW_ORGANIZATION_ID}
SCW_REGION=${SCW_REGION}
DD_API_KEY=${DD_API_KEY}
DD_SITE=${DD_SITE}
EOF

  # Deploy to Instance
  log "Deploying to Instance at ${SCW_INSTANCE_IP}..."

  # shellcheck disable=SC2086
  ssh $ssh_opts "root@${SCW_INSTANCE_IP}" \
    "systemctl stop opentelemetry-collector 2>/dev/null || true && mkdir -p /etc/opentelemetry-collector /usr/local/bin"

  # shellcheck disable=SC2086
  scp $ssh_opts \
    "$work_dir/otelcol-audit-trail" \
    "root@${SCW_INSTANCE_IP}:/usr/local/bin/otelcol-audit-trail"

  # shellcheck disable=SC2086
  scp $ssh_opts \
    "$work_dir/config.yaml" \
    "$work_dir/collector.env" \
    "root@${SCW_INSTANCE_IP}:/etc/opentelemetry-collector/"

  # shellcheck disable=SC2086
  scp $ssh_opts \
    "$work_dir/opentelemetry-collector.service" \
    "root@${SCW_INSTANCE_IP}:/etc/systemd/system/opentelemetry-collector.service"

  # Set permissions and start service
  # shellcheck disable=SC2086
  ssh $ssh_opts "root@${SCW_INSTANCE_IP}" \
    "chmod +x /usr/local/bin/otelcol-audit-trail && \
     chmod 600 /etc/opentelemetry-collector/collector.env && \
     systemctl daemon-reload && \
     systemctl enable opentelemetry-collector && \
     systemctl restart opentelemetry-collector"

  ok "Audit trail collector deployed and running on ${SCW_INSTANCE_IP}"
  ok "Verify: ssh root@${SCW_INSTANCE_IP} journalctl -fu opentelemetry-collector"
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

  provision_iam_application

  setup_cockpit_exports
  echo

  if [[ "$ENABLE_AUDIT_TRAIL" == "true" ]]; then
    setup_audit_trail || true
    echo
  fi

  register_datadog_account

  ok "Setup complete."
  print_datadog_credentials
}

main "$@"
