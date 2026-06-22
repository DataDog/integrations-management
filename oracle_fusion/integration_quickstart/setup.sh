#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2026 Datadog, Inc.

# setup.sh — Oracle Fusion + EPM integration onboarding for Datadog.
# See README.md for usage, options, and examples.

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging ───────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}  •${NC} $*"; }
success() { echo -e "${GREEN}  ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}  ⚠${NC} $*"; }
step()    { echo -e "\n${BOLD}━━━ $* ━━━${NC}"; }

fatal() {
    local message="$1"; shift
    echo -e "\n${RED}${BOLD}  ✗ FAILED: ${message}${NC}"
    if [[ $# -gt 0 ]]; then
        echo -e "${YELLOW}${BOLD}  How to fix:${NC}"
        for line in "$@"; do
            echo -e "  → ${line}"
        done
    fi
    echo -e "  → Once resolved, rerun the script to continue."
    echo ""
    exit 1
}

# ── Argument parsing ──────────────────────────────────────────────────────────
IDENTITY_DOMAIN_URL=""
FUSION_APP_ID=""
EPM_APP_ID=""
FUSION_BASE_URL=""
EPM_BASE_URL=""
FUSION_SCOPE=""
EPM_SCOPE=""
FUSION_ADMIN_USERNAME=""
FUSION_ADMIN_PASSWORD=""
ACCOUNT_NAME=""
USER_EMAIL=""
CONFIDENTIAL_APP_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity-domain-url)        IDENTITY_DOMAIN_URL="$2";   shift 2 ;;
        --fusion-app-id)              FUSION_APP_ID="$2";         shift 2 ;;
        --epm-app-id)                 EPM_APP_ID="$2";            shift 2 ;;
        --fusion-base-url)            FUSION_BASE_URL="$2";       shift 2 ;;
        --epm-base-url)               EPM_BASE_URL="$2";          shift 2 ;;
        --fusion-admin-username)      FUSION_ADMIN_USERNAME="$2"; shift 2 ;;
        --fusion-admin-password)      FUSION_ADMIN_PASSWORD="$2"; shift 2 ;;
        --user-email)                 USER_EMAIL="$2";            shift 2 ;;
        --account-name)               ACCOUNT_NAME="$2";          shift 2 ;;
        --confidential-application-id) CONFIDENTIAL_APP_ID="$2"; shift 2 ;;
--help|-h)
            cat <<'EOF'
Usage: ./setup.sh [OPTIONS]

Automates Oracle Fusion / EPM integration onboarding for Datadog.

Fresh Fusion + EPM onboarding (no --account-name):
  --identity-domain-url URL     OCI IAM identity domain URL (required)
  --fusion-app-id ID            Fusion SaaS app ID in OCI IAM (required for Fusion)
  --epm-app-id ID               EPM SaaS app ID in OCI IAM (required for EPM)
  --fusion-base-url URL         Fusion environment base URL (required for Fusion)
  --fusion-admin-username USER  Fusion admin username (required for Fusion)
  --fusion-admin-password PASS  Fusion admin password (required for Fusion)
  --epm-base-url URL            EPM environment base URL (required for EPM)
  --confidential-application-id ID  Existing confidential app ID (if not named "Datadog Fusion Integration")
  --user-email EMAIL            Email to attach to the created integration user

Add EPM to an existing Fusion account (--account-name):
  --account-name NAME           Existing Datadog Fusion account name
  --fusion-app-id ID            Fusion SaaS app ID in OCI IAM (required)
  --epm-app-id ID               EPM SaaS app ID in OCI IAM (required)
  --epm-base-url URL            EPM environment base URL (required if not already set)
  --confidential-application-id ID  Existing confidential app ID (if not named "Datadog Fusion Integration")

Environment variables:
  DD_API_KEY   Datadog API key (required)
  DD_APP_KEY   Datadog application key (required)
  DD_SITE      Datadog site, e.g. datadoghq.com (default: datadoghq.com)

See README.md for full details and examples.
EOF
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── URL normalisation ─────────────────────────────────────────────────────────
normalise_url() {
    local url="$1"
    url="${url%/}"           # strip trailing slash
    url="${url%:443}"        # strip trailing :443
    echo "$url"
}

[[ -n "$IDENTITY_DOMAIN_URL" ]] && IDENTITY_DOMAIN_URL=$(normalise_url "$IDENTITY_DOMAIN_URL")
[[ -n "$FUSION_BASE_URL" ]]     && FUSION_BASE_URL=$(normalise_url "$FUSION_BASE_URL")
[[ -n "$EPM_BASE_URL" ]]        && EPM_BASE_URL=$(normalise_url "$EPM_BASE_URL")
TOKEN_URL=""

# ── Datadog API helper ────────────────────────────────────────────────────────
DD_SITE="${DD_SITE:-datadoghq.com}"

dd_request() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-sS -w $'\n%{http_code}'
        -H "DD-API-KEY: ${DD_API_KEY:-}"
        -H "DD-APPLICATION-KEY: ${DD_APP_KEY:-}")
    [[ "$method" != "GET" ]] && args+=(-X "$method")
    [[ -n "$body" ]] && args+=(-H "Content-Type: application/json" -d "$body")
    local resp http_code body_out
    resp=$(curl "${args[@]}" "https://api.${DD_SITE}${path}")
    http_code="${resp##*$'\n'}"
    body_out="${resp%$'\n'*}"
    if [[ "$http_code" -ge 400 ]]; then
        printf '%s\n' "$body_out" >&2; return 1
    fi
    printf '%s\n' "$body_out"
}
dd_get()   { dd_request GET   "$1"; }
dd_post()  { dd_request POST  "$1" "$2"; }
dd_patch() { dd_request PATCH "$1" "$2"; }

# ── State tracking ────────────────────────────────────────────────────────────
CLIENT_ID=""
CLIENT_SECRET=""
FUSION_USER_ID=""
OCI_IAM_USER_ID=""

# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}Datadog Oracle Fusion / EPM Integration Onboarding${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ══════════════════════════════════════════════════════════════════════════════
step "PREREQUISITE CHECKS"

# 1. Required arguments
info "Checking required inputs..."
# IDENTITY_DOMAIN_URL may be omitted when --account-name names an existing DD account;
# it will be derived from the account's token_url after DD credentials are validated.
if [[ -z "$IDENTITY_DOMAIN_URL" && -z "$ACCOUNT_NAME" ]]; then
    fatal "--identity-domain-url is required" \
        "Provide your OCI IAM identity domain URL." \
        "Find it at: OCI Console → Identity & Security → Domains → copy the Domain URL" \
        "Or provide --account-name to look up an existing Datadog account and derive the URL automatically."
fi

if [[ -z "$FUSION_APP_ID" && -z "$EPM_APP_ID" ]]; then
    fatal "At least one of --fusion-app-id or --epm-app-id is required" \
        "Find these in: OCI Console → Domains → Oracle Cloud Services" \
        "Click on the Fusion or EPM app → copy the Application ID"
fi
if [[ -n "$ACCOUNT_NAME" ]]; then
    _account_name_forbidden=()
    [[ -n "$IDENTITY_DOMAIN_URL" ]]    && _account_name_forbidden+=("--identity-domain-url")
    [[ -n "$FUSION_BASE_URL" ]]        && _account_name_forbidden+=("--fusion-base-url")
    [[ -n "$FUSION_ADMIN_USERNAME" ]]  && _account_name_forbidden+=("--fusion-admin-username")
    [[ -n "$FUSION_ADMIN_PASSWORD" ]]  && _account_name_forbidden+=("--fusion-admin-password")
    [[ -n "$USER_EMAIL" ]]             && _account_name_forbidden+=("--user-email")
    if [[ ${#_account_name_forbidden[@]} -gt 0 ]]; then
        fatal "Invalid flags provided with --account-name: ${_account_name_forbidden[*]}" \
            "When --account-name is provided, only the following flags are allowed:" \
            "  --fusion-app-id, --epm-app-id, --epm-base-url, --confidential-application-id"
    fi
    [[ -z "$FUSION_APP_ID" ]] && fatal \
        "--fusion-app-id is required when --account-name is provided" \
        "When --account-name is provided, only adding EPM to an existing Fusion account is supported."
    [[ -z "$EPM_APP_ID" ]] && fatal \
        "--epm-app-id is required when --account-name is provided" \
        "When --account-name is provided, only adding EPM to an existing Fusion account is supported."
fi

[[ -z "$FUSION_APP_ID" ]] && warn "No --fusion-app-id provided — skipping Fusion scope"
# Fusion base URL and admin credentials are only required for fresh Fusion provisioning.
# When --account-name is provided and the account already has Fusion, these are not needed
# (Fusion user and role are already set up). We check this after back-fill below.
if [[ -n "$FUSION_APP_ID" && -z "$ACCOUNT_NAME" ]]; then
    [[ -z "$FUSION_BASE_URL" ]] && fatal \
        "--fusion-base-url is required when --fusion-app-id is provided" \
        "Provide your Oracle Fusion environment URL, e.g. https://icjnjb.fa.ocs.oraclecloud.com"
    [[ -z "$FUSION_ADMIN_USERNAME" ]] && fatal \
        "--fusion-admin-username is required for Fusion user provisioning" \
        "Provide a Fusion admin account username. These credentials are used only for" \
        "provisioning and are never stored by Datadog."
    [[ -z "$FUSION_ADMIN_PASSWORD" ]] && fatal \
        "--fusion-admin-password is required for Fusion user provisioning"
fi

[[ -z "$EPM_APP_ID" ]] && warn "No --epm-app-id provided — skipping EPM provisioning"
if [[ -n "$EPM_APP_ID" && -z "$ACCOUNT_NAME" ]]; then
    [[ -z "$EPM_BASE_URL" ]] && fatal \
        "--epm-base-url is required when --epm-app-id is provided" \
        "Provide your Oracle Fusion EPM environment URL," \
        "e.g. https://epmprod-xx.epm.us-ashburn-1.ocs.oraclecloud.com"
fi
success "Required inputs present"

# 2. Datadog credentials
info "Checking Datadog credentials..."
[[ -z "${DD_API_KEY:-}" ]] && fatal \
    "DD_API_KEY is required" \
    "Export your Datadog API key: export DD_API_KEY=<your-api-key>" \
    "Generate one at: https://app.datadoghq.com/organization-settings/api-keys"
[[ -z "${DD_APP_KEY:-}" ]] && fatal \
    "DD_APP_KEY is required" \
    "Export your Datadog application key: export DD_APP_KEY=<your-app-key>" \
    "Generate one at: https://app.datadoghq.com/organization-settings/application-keys"
dd_get "/api/v2/web-integrations/oracle-fusion/accounts" > /dev/null 2>&1 || fatal \
    "Datadog application or API key is invalid or unreachable (site: ${DD_SITE})" \
    "Verify DD_API_KEY and DD_APP_KEY are correct." \
    "Verify DD_SITE matches your Datadog site (e.g. datadoghq.com, datadoghq.eu, us3.datadoghq.com)"
success "Datadog credentials valid"

# If --account-name was given, fetch the existing account to back-fill credentials and URLs.
# When --identity-domain-url is also provided it is kept; otherwise it is derived from token_url.
if [[ -n "$ACCOUNT_NAME" ]]; then
    info "Fetching existing Datadog account '${ACCOUNT_NAME}'..."
    _accounts_resp=$(dd_get "/api/v2/web-integrations/oracle-fusion/accounts") || fatal \
        "Failed to list Datadog Oracle Fusion accounts" \
        "Verify DD_APP_KEY have 'integrations_read' permissions."
    _account_fields=$(echo "$_accounts_resp" | ACCOUNT_NAME="$ACCOUNT_NAME" python3 -c "
import sys, json, os
data = json.load(sys.stdin).get('data', [])
matched = [a for a in data if a.get('attributes', {}).get('name') == os.environ['ACCOUNT_NAME']]
if matched:
    s = matched[0].get('attributes', {}).get('settings', {})
    print('|'.join([
        s.get('client_id', ''),
        s.get('token_url', ''),
        s.get('fusion_base_url', ''),
        s.get('oauth_scope', ''),
        s.get('epm_base_url', ''),
        s.get('epm_oauth_scope', ''),
    ]))
else:
    print('|||||')
" 2>/dev/null)
    _fetched_client_id=$(echo "$_account_fields"   | cut -d'|' -f1)
    _fetched_token_url=$(echo "$_account_fields"   | cut -d'|' -f2)
    _fetched_fusion_base=$(echo "$_account_fields" | cut -d'|' -f3)
    _fetched_fusion_scope=$(echo "$_account_fields"| cut -d'|' -f4)
    _fetched_epm_base=$(echo "$_account_fields"    | cut -d'|' -f5)
    _fetched_epm_scope=$(echo "$_account_fields"   | cut -d'|' -f6)
    [[ -z "$_fetched_client_id" ]] && fatal \
        "No Datadog Oracle Fusion account named '${ACCOUNT_NAME}' found" \
        "Verify the account name matches exactly what is shown in the Datadog integration tile." \
        "Run without --account-name to create a new account instead."
    CLIENT_ID="$_fetched_client_id"
    if [[ -z "$IDENTITY_DOMAIN_URL" ]]; then
        IDENTITY_DOMAIN_URL=$(TOKEN_URL="$_fetched_token_url" python3 -c "
import os
from urllib.parse import urlparse
u = urlparse(os.environ['TOKEN_URL'])
print(u.scheme + '://' + u.netloc)
" 2>/dev/null)
        IDENTITY_DOMAIN_URL=$(normalise_url "$IDENTITY_DOMAIN_URL")
    fi
    TOKEN_URL="$_fetched_token_url"
    # Back-fill any existing account fields not supplied on this run so the PATCH
    # payload doesn't wipe the other product's settings.
    [[ -z "$FUSION_BASE_URL" ]] && FUSION_BASE_URL="$_fetched_fusion_base"
    [[ -z "$FUSION_SCOPE" ]]    && FUSION_SCOPE="$_fetched_fusion_scope"
    [[ -z "$EPM_BASE_URL" ]]    && EPM_BASE_URL="$_fetched_epm_base"
    [[ -z "$EPM_SCOPE" ]]       && EPM_SCOPE="$_fetched_epm_scope"
    # Only adding EPM to an existing Fusion account is supported via --account-name.
    [[ -z "$_fetched_fusion_base" ]] && fatal \
        "Account '${ACCOUNT_NAME}' does not have a Fusion integration configured" \
        "Adding EPM via --account-name is only supported for existing Fusion accounts." \
        "To set up a new Fusion + EPM account, run without --account-name."
    FUSION_ALREADY_PROVISIONED=true
    # EPM base URL is required if it's not already set on the account.
    if [[ -n "$EPM_APP_ID" && -z "$_fetched_epm_base" ]]; then
        [[ -z "$EPM_BASE_URL" ]] && fatal \
            "--epm-base-url is required when adding EPM to an existing account" \
            "Provide your Oracle Fusion EPM environment URL," \
            "e.g. https://epmprod-xx.epm.us-ashburn-1.ocs.oraclecloud.com"
    fi
    success "Account found — client_id: ${CLIENT_ID}, identity domain: ${IDENTITY_DOMAIN_URL}"
fi
FUSION_ALREADY_PROVISIONED="${FUSION_ALREADY_PROVISIONED:-false}"

[[ -z "$IDENTITY_DOMAIN_URL" ]] && fatal \
    "--identity-domain-url is required" \
    "Provide your OCI IAM identity domain URL." \
    "Find it at: OCI Console → Identity & Security → Domains → copy the Domain URL"
# TOKEN_URL is set here, after IDENTITY_DOMAIN_URL is fully resolved (either from --identity-domain-url or --account-name)
[[ -z "$TOKEN_URL" ]] && TOKEN_URL="${IDENTITY_DOMAIN_URL}/oauth2/v1/token"

# 3. Required tools
info "Checking required tools..."
if ! command -v python3 &>/dev/null; then
    fatal "python3 is required but not found" \
        "Install Python 3: https://www.python.org/downloads/" \
        "On macOS: brew install python3" \
        "On Debian/Ubuntu: apt-get install python3"
fi
if ! command -v curl &>/dev/null; then
    fatal "curl is required but not found"
fi
success "Required tools present"

# 4. OCI CLI configured
info "Checking OCI CLI credentials..."
if ! oci iam region list --output json > /dev/null 2>&1; then
    fatal "OCI CLI credentials are invalid or not configured" \
        "Run: oci setup config" \
        "Your OCI user must have identity domain administrator permissions." \
        "Docs: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"
fi
success "OCI CLI credentials valid"

# 5. Fusion app ID resolves in identity domain
if [[ -n "$FUSION_APP_ID" ]]; then
    info "Verifying Fusion app ID '${FUSION_APP_ID}' exists in identity domain..."
    fusion_app_resp=$(oci identity-domains apps list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "id eq \"${FUSION_APP_ID}\"" \
        --output json 2>/dev/null) || true
    fusion_app_name=$(echo "$fusion_app_resp" | python3 -c "
import sys,json
try:
    apps = json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('display-name','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)
    [[ -z "$fusion_app_name" ]] && fatal \
        "Fusion app ID '${FUSION_APP_ID}' was not found in identity domain '${IDENTITY_DOMAIN_URL}'" \
        "Verify the Application ID at: OCI Console → Domains → Oracle Cloud Services → Fusion Apps Cloud Service" \
        "Ensure you are using the hex Application ID, not the OCID."
    FUSION_SCOPE=$(echo "$fusion_app_resp" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    app=apps[0] if apps else {}
    audience=app.get('audience','')
    if not audience:
        print('urn:opc:resource:consumer::all')
    elif audience.endswith('consumer::all'):
        print(audience)
    else:
        print(audience + 'urn:opc:resource:consumer::all')
except Exception:
    print('')
" 2>/dev/null) || true
    [[ -z "$FUSION_SCOPE" ]] && fatal \
        "Failed to derive OAuth scope from Fusion app '${FUSION_APP_ID}'" \
        "Verify the app exists and your OCI credentials have permission to read it."
    success "Fusion app found: '${fusion_app_name}' — scope derived"
fi

# 6. EPM app ID resolves in identity domain
if [[ -n "$EPM_APP_ID" ]]; then
    info "Verifying EPM app ID '${EPM_APP_ID}' exists in identity domain..."
    epm_app_resp=$(oci identity-domains apps list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "id eq \"${EPM_APP_ID}\"" \
        --output json 2>/dev/null) || true
    epm_app_name=$(echo "$epm_app_resp" | python3 -c "
import sys,json
try:
    apps = json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('display-name','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)
    [[ -z "$epm_app_name" ]] && fatal \
        "EPM app ID '${EPM_APP_ID}' was not found in identity domain '${IDENTITY_DOMAIN_URL}'" \
        "Verify the Application ID at: OCI Console → Domains → Oracle Cloud Services → your EPM app" \
        "Ensure you are using the hex Application ID, not the OCID."
    EPM_SCOPE=$(echo "$epm_app_resp" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    app=apps[0] if apps else {}
    audience=app.get('audience','')
    if not audience:
        print('urn:opc:resource:consumer::all')
    elif audience.endswith('consumer::all'):
        print(audience)
    else:
        print(audience + 'urn:opc:resource:consumer::all')
except Exception:
    print('')
" 2>/dev/null) || true
    [[ -z "$EPM_SCOPE" ]] && fatal \
        "Failed to derive OAuth scope from EPM app '${EPM_APP_ID}'" \
        "Verify the app exists and your OCI credentials have permission to read it."
    success "EPM app found: '${epm_app_name}' — scope derived"
fi

# 7. Validate Fusion admin credentials + connectivity
if [[ -n "$FUSION_APP_ID" && "$FUSION_ALREADY_PROVISIONED" != true ]]; then
    info "Validating Fusion admin credentials and connectivity..."
    fusion_auth_status=$(curl -s --compressed -o /dev/null -w "%{http_code}" \
        "${FUSION_BASE_URL}/hcmRestApi/scim/Users?count=1" \
        -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" 2>/dev/null) || true
    if [[ "$fusion_auth_status" == "000" ]]; then
        fatal "Cannot reach Fusion at '${FUSION_BASE_URL}'" \
            "Check that the URL is correct and reachable from this machine." \
            "Try: curl -I ${FUSION_BASE_URL}/hcmRestApi/scim/Users"
    elif [[ "$fusion_auth_status" == "401" || "$fusion_auth_status" == "403" ]]; then
        fatal "Fusion admin credentials rejected (HTTP ${fusion_auth_status})" \
            "Verify --fusion-admin-username and --fusion-admin-password are correct." \
            "The admin account must have HCM user management permissions."
    fi
    success "Fusion admin credentials valid (HTTP ${fusion_auth_status})"
fi

# 8. EPM URL reachable
if [[ -n "$EPM_APP_ID" ]]; then
    info "Checking EPM URL reachability..."
    epm_status=$(curl -s -o /dev/null -w "%{http_code}" \
        "${EPM_BASE_URL}/HyperionPlanning/rest/v3/applications" 2>/dev/null) || true
    [[ "$epm_status" == "000" ]] && fatal \
        "Cannot reach EPM at '${EPM_BASE_URL}'" \
        "Check that the EPM base URL is correct and reachable from this machine."
    success "EPM URL reachable (HTTP ${epm_status})"
fi

# 9. DD_INTEGRATION_ROLE exists in Fusion and is accessible via API
#    We check the role CODE (the 'name' field in SCIM).
#    The role code must be exactly 'DD_INTEGRATION_ROLE'.
if [[ -n "$FUSION_APP_ID" && "$FUSION_ALREADY_PROVISIONED" != true ]]; then
    info "Checking for role with code 'DD_INTEGRATION_ROLE' in Fusion..."
    info "(The role CODE must be exactly 'DD_INTEGRATION_ROLE')"
    role_check=$(curl -s --compressed \
        "${FUSION_BASE_URL}/hcmRestApi/scim/Roles?filter=name+eq+%22DD_INTEGRATION_ROLE%22" \
        -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
        -H "Accept: application/json" 2>/dev/null) || true
    role_count=$(echo "$role_check" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('totalResults') or len(d.get('Resources',[])))
except Exception:
    print('')
" 2>/dev/null)
    if [[ -z "$role_count" || "$role_count" == "0" ]]; then
        fatal "No role with code 'DD_INTEGRATION_ROLE' was found in Fusion or it is not API-assignable" \
            "This custom role must be created in Oracle Fusion Security Console manually due to Oracle Fusion endpoint limitations. This is the last manual step required for integration onboarding." \
            "Steps:" \
            "  1. Log in to Oracle Fusion as an administrator" \
            "  2. Navigate to: Navigator → Tools → Security Console → Roles → Create Role" \
            "  3. Set the following:" \
            "       Role Name:     (any descriptive name)" \
            "       Role Code:     DD_INTEGRATION_ROLE  ← must be exactly this" \
            "       Role Category: Default" \
            "  4. Under 'Role Hierarchy', add these 3 roles by their codes:" \
            "       ESSMonitor" \
            "       ORA_FND_INTEGRATION_SPECIALIST_JOB" \
            "       ORA_FND_INTERNAL_AUDITOR_JOB" \
            "     Note: Fusion will likely pull in sub-roles automatically for each of these." \
            "     This is expected — keep all sub-roles that are added." \
            "  5. Save the role" \
            "  6. Make the role API-assignable via Role Provisioning Rules:" \
            "     Setup and Maintenance → search 'Manage Role Provisioning Rules' → open it" \
            "     Click 'Add' to create a new mapping:" \
            "       Mapping Name: DD Integration Role Mapping (or any name)" \
            "       From Date:    today's date" \
            "       Conditions:   leave all blank" \
            "     Under 'Associated Roles' → Add Row → search DD_INTEGRATION_ROLE" \
            "     Check 'Requestable' → leave other checkboxes unchecked → Save and Close" \
            "  Note: if the role and mapping already exist, this check can fail transiently — try re-running the script before making changes."
    fi
    DD_INTEGRATION_ROLE_ID=$(echo "$role_check" | python3 -c "
import sys,json; rs=json.load(sys.stdin).get('Resources',[]); print(rs[0].get('id','') if rs else '')
" 2>/dev/null)
    success "'DD_INTEGRATION_ROLE' found and accessible via API"
fi

# 10. Idempotency — check if confidential app already exists
APP_NAME="Datadog Fusion Integration"
info "Checking if '${APP_NAME}' already exists in OCI IAM..."
existing_app=$(oci identity-domains apps list \
    --endpoint "$IDENTITY_DOMAIN_URL" \
    --filter "displayName eq \"${APP_NAME}\"" \
    --output json 2>/dev/null) || true
existing_client_id=$(echo "$existing_app" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('name','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)
existing_app_ocid=$(echo "$existing_app" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('ocid','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)

APP_EXISTS=false
if [[ -n "$existing_client_id" ]]; then
    APP_EXISTS=true
    CLIENT_ID="$existing_client_id"
    warn "Confidential application '${APP_NAME}' already exists — reusing (client_id: ${CLIENT_ID})"
elif [[ -n "$ACCOUNT_NAME" && -z "$CONFIDENTIAL_APP_ID" ]]; then
    fatal "No confidential application named '${APP_NAME}' was found in this identity domain" \
        "When using --account-name, the confidential application must already exist." \
        "If your app has a different name, provide its ID with --confidential-application-id." \
        "Find the application ID in OCI Console → Domains → Integrated Applications."
elif [[ -n "$CONFIDENTIAL_APP_ID" ]]; then
    info "Looking up confidential app by ID '${CONFIDENTIAL_APP_ID}'..."
    conf_app_resp=$(oci identity-domains apps list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "id eq \"${CONFIDENTIAL_APP_ID}\"" \
        --output json 2>/dev/null) || true
    conf_app_client_id=$(echo "$conf_app_resp" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('name','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)
    conf_app_ocid=$(echo "$conf_app_resp" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    print(apps[0].get('ocid','') if apps else '')
except Exception:
    print('')
" 2>/dev/null)
    [[ -z "$conf_app_client_id" ]] && fatal \
        "Confidential application '${CONFIDENTIAL_APP_ID}' was not found in identity domain '${IDENTITY_DOMAIN_URL}'" \
        "Verify the application ID at: OCI Console → Domains → Integrated Applications"
    APP_EXISTS=true
    CLIENT_ID="$conf_app_client_id"
    existing_app_ocid="$conf_app_ocid"
    existing_app="$conf_app_resp"
    warn "Using provided confidential app — client_id: ${CLIENT_ID}"
fi

# 11. Idempotency — check if user already exists
#    For Fusion+EPM: check Fusion SCIM (user was created there)
#    For EPM-only: check OCI IAM directly (user created there instead)
FUSION_USER_EXISTS=false
OCI_IAM_USER_EXISTS=false
if [[ -n "$CLIENT_ID" ]]; then
    if [[ -n "$FUSION_APP_ID" ]]; then
        if [[ "$FUSION_ALREADY_PROVISIONED" == true ]]; then
            FUSION_USER_EXISTS=true
            info "Fusion user already provisioned — skipping check"
        else
            info "Checking if Fusion user '${CLIENT_ID}' already exists..."
            existing_user=$(curl -s --compressed \
                "${FUSION_BASE_URL}/hcmRestApi/scim/Users?filter=userName+eq+%22${CLIENT_ID}%22" \
                -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
                -H "Accept: application/json" 2>/dev/null) || true
            existing_user_id=$(echo "$existing_user" | python3 -c "
import sys,json
try: rs=json.load(sys.stdin).get('Resources',[]); print(rs[0].get('id','') if rs else '')
except Exception: print('')
" 2>/dev/null) || true
            if [[ -n "$existing_user_id" ]]; then
                FUSION_USER_EXISTS=true
                FUSION_USER_ID="$existing_user_id"
                warn "Fusion user already exists (id: ${FUSION_USER_ID}) — skipping creation"
            fi
        fi
    else
        info "Checking if OCI IAM user '${CLIENT_ID}' already exists..."
        existing_oci_user=$(oci identity-domains users list \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --filter "userName eq \"${CLIENT_ID}\"" \
            --output json 2>/dev/null) || true
        existing_oci_user_id=$(echo "$existing_oci_user" | python3 -c "
import sys,json
rs=json.load(sys.stdin).get('data',{}).get('resources',[])
print(rs[0].get('id','') if rs else '')
" 2>/dev/null)
        if [[ -n "$existing_oci_user_id" ]]; then
            OCI_IAM_USER_EXISTS=true
            OCI_IAM_USER_ID="$existing_oci_user_id"
            warn "OCI IAM user already exists (id: ${OCI_IAM_USER_ID}) — skipping creation"
        fi
    fi
fi

success "Prerequisite checks passed"

# ══════════════════════════════════════════════════════════════════════════════
step "STEP 1: CREATE CONFIDENTIAL APPLICATION"

if [[ "$APP_EXISTS" == true ]]; then
    info "Using existing app (client_id: ${CLIENT_ID})"
    # Derive existing scopes from the OCI app response.
    # OCI apps list does not always include allowed-scopes; fall back to empty.
    existing_scopes=$(echo "$existing_app" | python3 -c "
import sys,json
try:
    apps=json.load(sys.stdin).get('data',{}).get('resources',[])
    scopes=[s.get('fqs','') for s in (apps[0].get('allowed-scopes',[]) if apps else [])]
    print(' '.join(scopes))
except Exception:
    print('')
" 2>/dev/null) || true

    # Add Fusion scope to the existing app if not already present
    if [[ -n "${FUSION_SCOPE:-}" && -n "$existing_app_ocid" ]]; then
        if echo "$existing_scopes" | grep -qF "${FUSION_SCOPE}"; then
            info "Fusion scope already present on app — skipping"
        else
            info "Adding Fusion scope to existing confidential app..."
            _new_scopes=$(FUSION_SCOPE="${FUSION_SCOPE}" EPM_SCOPE="${EPM_SCOPE:-}" python3 -c "
import os,json
scopes=[]
if os.environ.get('FUSION_SCOPE'): scopes.append({'fqs':os.environ['FUSION_SCOPE']})
if os.environ.get('EPM_SCOPE'):    scopes.append({'fqs':os.environ['EPM_SCOPE']})
print(json.dumps(scopes))
")
            oci identity-domains app patch \
                --endpoint "$IDENTITY_DOMAIN_URL" \
                --app-id "$existing_app_ocid" \
                --schemas '["urn:ietf:params:scim:api:messages:2.0:PatchOp"]' \
                --operations "[
                    {\"op\": \"replace\", \"path\": \"allowedScopes\",   \"value\": ${_new_scopes}},
                    {\"op\": \"replace\", \"path\": \"isOAuthClient\",   \"value\": true},
                    {\"op\": \"replace\", \"path\": \"allowedGrants\",   \"value\": [\"client_credentials\"]},
                    {\"op\": \"replace\", \"path\": \"clientType\",      \"value\": \"confidential\"},
                    {\"op\": \"replace\", \"path\": \"clientIPChecking\",\"value\": \"anywhere\"},
                    {\"op\": \"replace\", \"path\": \"bypassConsent\",   \"value\": true},
                    {\"op\": \"replace\", \"path\": \"active\",          \"value\": true}
                ]" \
                --output json > /dev/null 2>/dev/null || fatal \
                "Failed to update existing confidential app" \
                "Ensure your OCI credentials have 'Identity Domain Administrator' permissions."
            success "Fusion scope added and app configuration verified"
            # Update existing_scopes so the EPM check below doesn't re-patch unnecessarily
            existing_scopes="${FUSION_SCOPE} ${EPM_SCOPE:-}"
        fi
    fi

    # Add EPM scope to the existing app if not already present
    if [[ -n "${EPM_SCOPE:-}" && -n "$existing_app_ocid" ]]; then
        if echo "$existing_scopes" | grep -qF "${EPM_SCOPE}"; then
            info "EPM scope already present on app — skipping"
        else
            info "Adding EPM scope to existing confidential app..."
            _new_scopes=$(FUSION_SCOPE="${FUSION_SCOPE:-}" EPM_SCOPE="${EPM_SCOPE}" python3 -c "
import os,json
scopes=[]
if os.environ.get('FUSION_SCOPE'): scopes.append({'fqs':os.environ['FUSION_SCOPE']})
if os.environ.get('EPM_SCOPE'):    scopes.append({'fqs':os.environ['EPM_SCOPE']})
print(json.dumps(scopes))
")
            oci identity-domains app patch \
                --endpoint "$IDENTITY_DOMAIN_URL" \
                --app-id "$existing_app_ocid" \
                --schemas '["urn:ietf:params:scim:api:messages:2.0:PatchOp"]' \
                --operations "[
                    {\"op\": \"replace\", \"path\": \"allowedScopes\",   \"value\": ${_new_scopes}},
                    {\"op\": \"replace\", \"path\": \"isOAuthClient\",   \"value\": true},
                    {\"op\": \"replace\", \"path\": \"allowedGrants\",   \"value\": [\"client_credentials\"]},
                    {\"op\": \"replace\", \"path\": \"clientType\",      \"value\": \"confidential\"},
                    {\"op\": \"replace\", \"path\": \"clientIPChecking\",\"value\": \"anywhere\"},
                    {\"op\": \"replace\", \"path\": \"bypassConsent\",   \"value\": true},
                    {\"op\": \"replace\", \"path\": \"active\",          \"value\": true}
                ]" \
                --output json > /dev/null 2>/dev/null || fatal \
                "Failed to update existing confidential app" \
                "Ensure your OCI credentials have 'Identity Domain Administrator' permissions."
            success "EPM scope added and app configuration verified"
        fi
    fi
else
    info "Building allowed scopes list..."
    SCOPES_JSON="["
    FIRST=true
    if [[ -n "${FUSION_SCOPE:-}" ]]; then
        SCOPES_JSON+="{\"fqs\": \"${FUSION_SCOPE}\"}"
        FIRST=false
    fi
    if [[ -n "${EPM_SCOPE:-}" ]]; then
        [[ "$FIRST" == false ]] && SCOPES_JSON+=", "
        SCOPES_JSON+="{\"fqs\": \"${EPM_SCOPE}\"}"
    fi
    SCOPES_JSON+="]"

    info "Creating confidential application '${APP_NAME}' in OCI IAM..."
    app_result=$(oci identity-domains app create \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --schemas '["urn:ietf:params:scim:schemas:oracle:idcs:App"]' \
        --display-name "$APP_NAME" \
        --description "Datadog integration for Oracle Fusion and Fusion EPM monitoring" \
        --based-on-template '{"value": "CustomWebAppTemplateId", "wellKnownId": "CustomWebAppTemplateId"}' \
        --is-o-auth-client true \
        --allowed-grants '["client_credentials"]' \
        --client-type "confidential" \
        --client-ip-checking "anywhere" \
        --bypass-consent true \
        --active true \
        --allowed-scopes "$SCOPES_JSON" \
        --output json 2>/dev/null) || fatal \
        "Failed to create confidential application in OCI IAM" \
        "Ensure your OCI credentials have 'Identity Domain Administrator' permissions." \
        "Check: OCI Console → Identity & Security → Domains → your domain → Administrators"

    CLIENT_ID=$(echo "$app_result" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('name',''))
" 2>/dev/null)
    APP_OCID=$(echo "$app_result" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('ocid',''))
" 2>/dev/null)
    CLIENT_SECRET=$(echo "$app_result" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('client-secret',''))
" 2>/dev/null)

    # If not in creation response, retrieve via app get
    if [[ -z "$CLIENT_SECRET" ]]; then
        CLIENT_SECRET=$(oci identity-domains app get \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --app-id "$APP_OCID" \
            --output json 2>/dev/null | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('client-secret',''))
" 2>/dev/null)
    fi

    [[ -z "$CLIENT_ID" ]] && fatal \
        "Application '${APP_NAME}' was created but its OAuth client ID could not be parsed from the OCI response" \
        "Find the application ID in OCI Console → Domains → Integrated Applications → '${APP_NAME}'" \
        "If your app has a non-standard name, re-run with: --confidential-application-id <application-id>"

    success "Confidential application created"
    echo ""
    echo -e "  ${BOLD}client_id:${NC}     ${CLIENT_ID}"
    echo -e "  ${BOLD}app_ocid:${NC}      ${APP_OCID}"
    if [[ -n "$CLIENT_SECRET" ]]; then
        echo -e "  ${BOLD}client_secret:${NC} ${CLIENT_SECRET}"
    else
        echo -e "  ${YELLOW}client_secret: retrieve from OCI Console → Domains → Integrated Applications → '${APP_NAME}' → OAuth Configuration${NC}"
    fi
    echo ""
fi

# ══════════════════════════════════════════════════════════════════════════════
# No Fusion app: create the user directly in OCI IAM (no Fusion SCIM needed)
# The OCI IAM user is required for the EPM Service Administrator grant in Step 4.
if [[ -z "$FUSION_APP_ID" && -n "$EPM_APP_ID" ]]; then

    step "STEP 2: CREATE OCI IAM USER (EPM-only)"

    if [[ "$OCI_IAM_USER_EXISTS" == true ]]; then
        info "Skipping — OCI IAM user already exists (id: ${OCI_IAM_USER_ID})"
    else
        info "Creating OCI IAM user with username '${CLIENT_ID}'..."
        _oci_emails_arg=()
        [[ -n "$USER_EMAIL" ]] && _oci_emails_arg=(--emails "[{\"value\": \"${USER_EMAIL}\", \"type\": \"work\", \"primary\": true}]")
        oci_user_result=$(oci identity-domains user create \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --schemas '["urn:ietf:params:scim:schemas:core:2.0:User"]' \
            --user-name "$CLIENT_ID" \
            --name '{"familyName": "Datadog Integration"}' \
            --active true \
            ${_oci_emails_arg[@]+"${_oci_emails_arg[@]}"} \
            --output json 2>/dev/null) || fatal \
            "Failed to create OCI IAM user '${CLIENT_ID}'" \
            "Ensure your OCI credentials have permission to create users in the identity domain." \
            "Check: OCI Console → Domains → Administrators"

        OCI_IAM_USER_ID=$(echo "$oci_user_result" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',''))
" 2>/dev/null)
        [[ -z "$OCI_IAM_USER_ID" ]] && fatal \
            "OCI IAM user was created but its ID could not be parsed from the OCI response" \
            "If the issue persists, contact Datadog support."
        success "OCI IAM user created (id: ${OCI_IAM_USER_ID})"
    fi

fi

# ══════════════════════════════════════════════════════════════════════════════
if [[ -n "$FUSION_APP_ID" && "$FUSION_ALREADY_PROVISIONED" != true ]]; then

    step "STEP 2: CREATE FUSION INTEGRATION USER"

    if [[ "$FUSION_USER_EXISTS" == true ]]; then
        info "Skipping — Fusion user already exists (id: ${FUSION_USER_ID})"
    else
        info "Creating Fusion user with username '${CLIENT_ID}'..."
        _fusion_user_body=$(CLIENT_ID="$CLIENT_ID" USER_EMAIL="${USER_EMAIL:-}" python3 -c "
import json, os
body = {
    'schemas': ['urn:scim:schemas:core:2.0:User'],
    'userName': os.environ['CLIENT_ID'],
    'name': {'familyName': 'Datadog Integration'},
    'active': True,
}
email = os.environ.get('USER_EMAIL', '')
if email:
    body['emails'] = [{'value': email, 'type': 'work', 'primary': True}]
print(json.dumps(body))
")
        user_response=$(curl -s --compressed -w $'\n%{http_code}' \
            -X POST "${FUSION_BASE_URL}/hcmRestApi/scim/Users" \
            -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d "$_fusion_user_body" 2>/dev/null)
        user_status="${user_response##*$'\n'}"
        user_body="${user_response%$'\n'*}"

        if [[ "$user_status" != "201" ]]; then
            fatal "Failed to create Fusion user (HTTP ${user_status})" \
                "Response: $(echo "${user_body}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("Errors",[{}])[0].get("description","unknown error"))' 2>/dev/null)" \
                "Ensure --fusion-admin-username has HCM User Management permissions." \
                "The admin must have the 'IT Security Manager' or equivalent role in Fusion."
        fi

        FUSION_USER_ID=$(echo "${user_body}" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('id',''))
")
        success "Fusion user created (internal id: ${FUSION_USER_ID})"
    fi

    # ══════════════════════════════════════════════════════════════════════════
    step "STEP 3: ASSIGN FUSION ROLE (DD_INTEGRATION_ROLE)"

    info "Assigning 'DD_INTEGRATION_ROLE' to user..."
    patch_result=$(curl -s --compressed -w "\n%{http_code}" \
        -X PATCH "${FUSION_BASE_URL}/hcmRestApi/scim/Roles/${DD_INTEGRATION_ROLE_ID}" \
        -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d "{
            \"schemas\": [\"urn:oracle:apps:scim:schemas:fa:1.0:Role\"],
            \"members\": [{\"value\": \"${FUSION_USER_ID}\", \"operation\": \"ADD\"}]
        }" 2>/dev/null)

    patch_status="${patch_result##*$'\n'}"
    patch_body="${patch_result%$'\n'*}"

    if [[ "$patch_status" != "204" && "$patch_status" != "200" ]]; then
        fatal "Failed to assign DD_INTEGRATION_ROLE (HTTP ${patch_status})" \
            "Verify that 'DD_INTEGRATION_ROLE' is marked Requestable in Role Provisioning Rules:" \
            "  Setup and Maintenance → search 'Manage Role Provisioning Rules' → open it" \
            "  Click 'Add' to create a new mapping:" \
            "    Mapping Name: DD Integration Role Mapping (or any name)" \
            "    From Date:    today's date" \
            "    Conditions:   leave all blank (applies to all users)" \
            "  Under 'Associated Roles' → Add Row → search DD_INTEGRATION_ROLE" \
            "  Check 'Requestable' → leave other checkboxes unchecked → Save and Close"
    fi
    success "DD_INTEGRATION_ROLE assigned to Fusion user"

fi

# ══════════════════════════════════════════════════════════════════════════════
if [[ -n "$EPM_APP_ID" ]]; then

    step "STEP 4: GRANT EPM SERVICE ADMINISTRATOR ROLE"

    # Look up OCI IAM user ID — retry up to 5 times with 10s sleep between attempts.
    # A Fusion user created in Step 2 may take a moment to propagate into OCI IAM.
    info "Looking up OCI IAM user ID for '${CLIENT_ID}'..."
    OCI_IAM_USER_ID=""
    for attempt in 1 2 3 4 5; do
        user_resp=$(oci identity-domains users list \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --filter "userName eq \"${CLIENT_ID}\"" \
            --output json 2>/dev/null)
        OCI_IAM_USER_ID=$(echo "$user_resp" | python3 -c "
import sys,json
rs=json.load(sys.stdin).get('data',{}).get('resources',[])
print(rs[0].get('id','') if rs else '')
" 2>/dev/null)
        if [[ -n "$OCI_IAM_USER_ID" ]]; then
            break
        fi
        if [[ $attempt -lt 5 ]]; then
            info "User not yet visible in OCI IAM — waiting 10 seconds (attempt ${attempt}/5)..."
            sleep 10
        fi
    done

    [[ -z "$OCI_IAM_USER_ID" ]] && fatal \
        "Could not find OCI IAM user with userName '${CLIENT_ID}' after 5 attempts (50 seconds)" \
        "The Fusion user may not have synced to OCI IAM yet." \
        "Wait a few minutes and re-run the script — it will pick up where it left off."

    success "OCI IAM user found (id: ${OCI_IAM_USER_ID})"

    # Find EPM Service Administrator role ID
    info "Finding EPM role..."
    SERVICE_ADMIN_ROLE_ID=$(oci identity-domains app-roles list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "app.value eq \"${EPM_APP_ID}\"" \
        --count 200 \
        --output json 2>/dev/null | python3 -c "
import sys, json
app_id = '${EPM_APP_ID}'
resources = json.load(sys.stdin).get('data', {}).get('resources', [])
matched = [r for r in resources
    if r.get('app', {}).get('value') == app_id
    and r.get('display-name', '').lower() == 'service administrator']
print(matched[0].get('id', '') if matched else '')
")

    [[ -z "$SERVICE_ADMIN_ROLE_ID" ]] && fatal \
        "Could not find 'Service Administrator' role for EPM app '${EPM_APP_ID}'" \
        "Verify the EPM app ID is correct." \
        "Check: OCI Console → Domains → Oracle Cloud Services → your EPM app → Application ID"

    success "EPM role found (id: ${SERVICE_ADMIN_ROLE_ID})"

    # Check if grant already exists
    info "Checking if EPM role grant already exists..."
    existing_grant=$(oci identity-domains grants list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "grantee.value eq \"${OCI_IAM_USER_ID}\" and app.value eq \"${EPM_APP_ID}\" and entitlement.attributeValue eq \"${SERVICE_ADMIN_ROLE_ID}\"" \
        --output json 2>/dev/null | python3 -c "
import sys,json
rs=json.load(sys.stdin).get('data',{}).get('resources',[])
print(len(rs))
" 2>/dev/null)

    if [[ "${existing_grant:-0}" -gt 0 ]]; then
        warn "EPM Service Administrator grant already exists — skipping"
    else
        info "Creating EPM role grant..."
        grant_result=$(oci identity-domains grant create \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --schemas '["urn:ietf:params:scim:schemas:oracle:idcs:Grant"]' \
            --grant-mechanism "ADMINISTRATOR_TO_USER" \
            --grantee "{\"type\": \"User\", \"value\": \"${OCI_IAM_USER_ID}\"}" \
            --app "{\"value\": \"${EPM_APP_ID}\"}" \
            --entitlement "{\"attributeName\": \"appRoles\", \"attributeValue\": \"${SERVICE_ADMIN_ROLE_ID}\"}" \
            --output json 2>/dev/null) || fatal \
            "Failed to create EPM Service Administrator grant" \
            "Ensure your OCI credentials have Identity Domain Administrator permissions." \
            "Check: OCI Console → Domains → Administrators"

        success "EPM role granted"
    fi

fi

# ══════════════════════════════════════════════════════════════════════════════
step "STEP 5: REGISTER DATADOG ACCOUNT"


# Default account name to the hostname from the Fusion or EPM base URL
if [[ -z "$ACCOUNT_NAME" ]]; then
    _base_url="${FUSION_BASE_URL:-${EPM_BASE_URL:-}}"
    ACCOUNT_NAME=$(python3 -c "
from urllib.parse import urlparse
print(urlparse('${_base_url}').hostname or '')
" 2>/dev/null)
    ACCOUNT_NAME="${ACCOUNT_NAME:-Oracle Fusion Integration}"
fi

info "Checking for existing Datadog Oracle Fusion account '${ACCOUNT_NAME}'..."
accounts_resp=$(dd_get "/api/v2/web-integrations/oracle-fusion/accounts") || fatal \
    "Failed to list Datadog Oracle Fusion accounts" \
    "Verify DD_APP_KEY have the 'integrations_read' and 'integrations_write' permissions."

existing_account_fields=$(echo "$accounts_resp" | ACCOUNT_NAME="$ACCOUNT_NAME" python3 -c "
import sys,json,os
data = json.load(sys.stdin).get('data', [])
matched = [a for a in data if a.get('attributes', {}).get('name') == os.environ['ACCOUNT_NAME']]
if matched:
    s = matched[0].get('attributes', {}).get('settings', {})
    print('|'.join([
        matched[0].get('id', ''),
        s.get('fusion_base_url', ''),
        s.get('oauth_scope', ''),
        s.get('epm_base_url', ''),
        s.get('epm_oauth_scope', ''),
    ]))
else:
    print('||||')
" 2>/dev/null)
existing_account_id=$(echo "$existing_account_fields"        | cut -d'|' -f1)
_existing_fusion_base=$(echo "$existing_account_fields"      | cut -d'|' -f2)
_existing_fusion_scope=$(echo "$existing_account_fields"     | cut -d'|' -f3)
_existing_epm_base=$(echo "$existing_account_fields"         | cut -d'|' -f4)
_existing_epm_scope=$(echo "$existing_account_fields"        | cut -d'|' -f5)


# Back-fill any existing account fields not supplied on this run so the PATCH
# payload doesn't wipe the other product's settings.
if [[ -n "$existing_account_id" ]]; then
    [[ -z "$FUSION_BASE_URL" ]] && FUSION_BASE_URL="$_existing_fusion_base"
    [[ -z "$FUSION_SCOPE" ]]    && FUSION_SCOPE="$_existing_fusion_scope"
    [[ -z "$EPM_BASE_URL" ]]    && EPM_BASE_URL="$_existing_epm_base"
    [[ -z "$EPM_SCOPE" ]]       && EPM_SCOPE="$_existing_epm_scope"
fi

# When reusing an existing confidential app for a new Datadog account, the client
# secret is not available from the creation response. Regenerate it so it can be
# included in the create payload (the API requires secrets on create).
if [[ "$APP_EXISTS" == true && -z "$CLIENT_SECRET" ]]; then
    info "Regenerating client secret for existing confidential app..."
    regen_resp=$(oci identity-domains app patch \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --app-id "$existing_app_ocid" \
        --schemas '["urn:ietf:params:scim:api:messages:2.0:PatchOp"]' \
        --operations '[{"op":"replace","path":"clientSecret","value":""}]' \
        --output json 2>/dev/null) || true
    CLIENT_SECRET=$(echo "$regen_resp" | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('data',{}).get('client-secret',''))
except Exception: print('')
" 2>/dev/null)
    [[ -z "$CLIENT_SECRET" ]] && fatal \
        "Could not retrieve client secret for existing confidential app '${APP_NAME}'" \
        "Retrieve the secret manually from OCI Console → Domains → Integrated Applications → '${APP_NAME}' → OAuth Configuration" \
        "If your app has a non-standard name, re-run with: --confidential-application-id <application-id>"
    success "Client secret regenerated"
fi

# Build payload — omit optional fields when values are absent;
# include client_secret when available (new app); omit when empty (PATCH keeps existing secret).
payload=$(CLIENT_ID="$CLIENT_ID" TOKEN_URL="$TOKEN_URL" \
    FUSION_SCOPE="${FUSION_SCOPE:-}" EPM_SCOPE="${EPM_SCOPE:-}" \
    FUSION_BASE_URL="${FUSION_BASE_URL:-}" EPM_BASE_URL="${EPM_BASE_URL:-}" \
    ACCOUNT_NAME="$ACCOUNT_NAME" CLIENT_SECRET="${CLIENT_SECRET:-}" python3 -c "
import json, os
settings = {
    'client_id': os.environ['CLIENT_ID'],
    'token_url':  os.environ['TOKEN_URL'],
}
fusion_scope = os.environ.get('FUSION_SCOPE', '')
epm_scope    = os.environ.get('EPM_SCOPE', '')
fusion_base  = os.environ.get('FUSION_BASE_URL', '')
epm_base     = os.environ.get('EPM_BASE_URL', '')
if fusion_scope: settings['oauth_scope']     = fusion_scope
if fusion_base:  settings['fusion_base_url'] = fusion_base
if epm_scope:    settings['epm_oauth_scope'] = epm_scope
if epm_base:     settings['epm_base_url']    = epm_base
enabled = []
if fusion_base: enabled += ['ess', 'audit']
if epm_base:    enabled += ['epm_jobs', 'epm_audit']
if enabled:
    settings['logs_config'] = {'enabled_services': enabled}
attrs = {'name': os.environ['ACCOUNT_NAME'], 'settings': settings}
client_secret = os.environ.get('CLIENT_SECRET', '')
if client_secret: attrs['secrets'] = {'client_secret': client_secret}
print(json.dumps({'data': {'type': 'Account', 'attributes': attrs}}))
" 2>/dev/null)

if [[ -n "$existing_account_id" ]]; then
    info "Account exists — updating (id=${existing_account_id})..."
    dd_patch "/api/v2/web-integrations/oracle-fusion/accounts/${existing_account_id}" "$payload" > /dev/null || fatal \
        "Failed to update Datadog Oracle Fusion account" \
        "Verify DD_APP_KEY have 'integrations_write' permissions." \
        "If credentials were just created or updated, try re-running the script — OCI changes can take a moment to propagate."
    success "Datadog Oracle Fusion account updated (id=${existing_account_id})"
else
    info "Creating Datadog Oracle Fusion account '${ACCOUNT_NAME}'..."
    create_resp=$(dd_post "/api/v2/web-integrations/oracle-fusion/accounts" "$payload") || fatal \
        "Failed to create Datadog Oracle Fusion account" \
        "Confirm an account named '${ACCOUNT_NAME}' does not already exist in the Datadog integration tile." \
        "Verify DD_APP_KEY have 'integrations_write' permissions." \
        "If credentials were just created or updated, try re-running the script — OCI changes can take a moment to propagate."
    new_account_id=$(echo "$create_resp" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',''))
" 2>/dev/null)
    success "Datadog Oracle Fusion account created (id=${new_account_id:-unknown})"
fi

# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}${BOLD}━━━ ONBOARDING COMPLETE ━━━${NC}"
echo ""
echo -e "  ${BOLD}Summary:${NC}"
echo -e "  account_name:    ${ACCOUNT_NAME}"
echo -e "  client_id:       ${CLIENT_ID}"
echo -e "  token_url:       ${TOKEN_URL}"
[[ -n "${FUSION_SCOPE:-}" ]] && echo -e "  fusion_scope:    ${FUSION_SCOPE}"
[[ -n "${EPM_SCOPE:-}" ]]    && echo -e "  epm_scope:       ${EPM_SCOPE}"
[[ -n "$FUSION_BASE_URL" ]]  && echo -e "  fusion_base_url: ${FUSION_BASE_URL}"
[[ -n "$EPM_BASE_URL" ]]     && echo -e "  epm_base_url:    ${EPM_BASE_URL}"
echo ""
echo -e "  Please allow at least 15 minutes for EPM roles to propagate before testing."
echo ""
if [[ -n "${EPM_BASE_URL:-}" ]]; then
    echo -e "  ${YELLOW}${BOLD}Note:${NC} To sync the EPM integration user with your account, sign in to your EPM"
    echo -e "  instance and navigate to Tools → Access Control → Role Assignment Report, and verify the"
    echo -e "  Datadog Integration user is present. Otherwise, EPM does not sync the user"
    echo -e "  automatically until the next automatic refresh."
    echo ""
fi
