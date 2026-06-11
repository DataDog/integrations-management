#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

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
    echo ""
    exit 1
}

# ── Argument parsing ──────────────────────────────────────────────────────────
IDENTITY_DOMAIN_URL=""
FUSION_APP_ID=""
EPM_APP_ID=""
FUSION_BASE_URL=""
EPM_BASE_URL=""
FUSION_ADMIN_USERNAME=""
FUSION_ADMIN_PASSWORD=""
RESUME=false
ACCOUNT_NAME=""
USER_EMAIL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity-domain-url)   IDENTITY_DOMAIN_URL="$2";   shift 2 ;;
        --fusion-app-id)         FUSION_APP_ID="$2";         shift 2 ;;
        --epm-app-id)            EPM_APP_ID="$2";            shift 2 ;;
        --fusion-base-url)       FUSION_BASE_URL="$2";       shift 2 ;;
        --epm-base-url)          EPM_BASE_URL="$2";          shift 2 ;;
        --fusion-admin-username) FUSION_ADMIN_USERNAME="$2"; shift 2 ;;
        --fusion-admin-password) FUSION_ADMIN_PASSWORD="$2"; shift 2 ;;
        --user-email)            USER_EMAIL="$2";            shift 2 ;;
        --account-name)          ACCOUNT_NAME="$2";          shift 2 ;;
        --resume)                RESUME=true;                shift 1 ;;
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
TOKEN_URL="${IDENTITY_DOMAIN_URL}/oauth2/v1/token"

# ── Datadog API helper ────────────────────────────────────────────────────────
DD_SITE="${DD_SITE:-datadoghq.com}"

dd_request() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-sS -w $'\n%{http_code}'
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
        "Find these in: OCI Console → Identity & Security → Domains → Applications" \
        "Click on the Fusion or EPM app → copy the Application ID"
fi

[[ -z "$FUSION_APP_ID" ]] && warn "No --fusion-app-id provided — skipping Fusion scope"
if [[ -n "$FUSION_APP_ID" ]]; then
    [[ -z "$FUSION_BASE_URL" ]] && [[ -n "$FUSION_APP_ID" ]] && fatal \
        "--fusion-base-url is required when --fusion-app-id is provided" \
        "Provide your Oracle Fusion environment URL, e.g. https://icjnjb.fa.ocs.oraclecloud.com"
    [[ -z "$FUSION_ADMIN_USERNAME" ]] && [[ -n "$FUSION_APP_ID" ]] && fatal \
        "--fusion-admin-username is required for Fusion user provisioning" \
        "Provide a Fusion admin account username. These credentials are used only for" \
        "provisioning and are never stored by Datadog."
    [[ -z "$FUSION_ADMIN_PASSWORD" ]] && [[ -n "$FUSION_APP_ID" ]] && fatal \
        "--fusion-admin-password is required for Fusion user provisioning"
fi

[[ -z "$EPM_APP_ID" ]] && warn "No --epm-app-id provided — skipping EPM provisioning"
if [[ -n "$EPM_APP_ID" ]]; then
    [[ -z "$EPM_BASE_URL" ]] && [[ -n "$EPM_APP_ID" ]] && fatal \
        "--epm-base-url is required when --epm-app-id is provided" \
        "Provide your Oracle Fusion EPM environment URL," \
        "e.g. https://epmprod-xx.epm.us-ashburn-1.ocs.oraclecloud.com"
fi
success "Required inputs present"

# 2. Datadog credentials
info "Checking Datadog credentials..."
[[ -z "${DD_APP_KEY:-}" ]] && fatal \
    "DD_APP_KEY is required" \
    "Export your Datadog application key: export DD_APP_KEY=<your-app-key>" \
    "Generate one at: https://app.datadoghq.com/organization-settings/application-keys"
dd_get "/api/v2/web-integrations/oracle-fusion/accounts" > /dev/null 2>&1 || fatal \
    "Datadog application key is invalid or unreachable (site: ${DD_SITE})" \
    "Verify DD_APP_KEY is correct." \
    "Verify DD_SITE matches your Datadog site (e.g. datadoghq.com, datadoghq.eu, us3.datadoghq.com)"
success "Datadog credentials valid"

# If --account-name was given without --identity-domain-url, fetch the existing account
# to obtain client_id and derive the identity domain URL.
if [[ -n "$ACCOUNT_NAME" && -z "$IDENTITY_DOMAIN_URL" ]]; then
    info "Fetching existing Datadog account '${ACCOUNT_NAME}'..."
    _accounts_resp=$(dd_get "/api/v2/web-integrations/oracle-fusion/accounts") || fatal \
        "Failed to list Datadog Oracle Fusion accounts" \
        "Verify DD_APP_KEY have 'integrations_read' permissions."
    _account_fields=$(echo "$_accounts_resp" | python3 -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
matched = [a for a in data if a.get('attributes', {}).get('name') == '${ACCOUNT_NAME}']
if matched:
    s = matched[0].get('attributes', {}).get('settings', {})
    print(s.get('client_id', '') + '|' + s.get('token_url', ''))
else:
    print('|')
" 2>/dev/null)
    _fetched_client_id="${_account_fields%%|*}"
    _fetched_token_url="${_account_fields##*|}"
    [[ -z "$_fetched_client_id" ]] && fatal \
        "No Datadog Oracle Fusion account named '${ACCOUNT_NAME}' found" \
        "Verify the account name matches exactly what is shown in the Datadog integration tile." \
        "Run without --account-name to create a new account instead."
    CLIENT_ID="$_fetched_client_id"
    IDENTITY_DOMAIN_URL=$(python3 -c "
from urllib.parse import urlparse
u = urlparse('${_fetched_token_url}')
print(u.scheme + '://' + u.netloc)
" 2>/dev/null)
    IDENTITY_DOMAIN_URL=$(normalise_url "$IDENTITY_DOMAIN_URL")
    TOKEN_URL="$_fetched_token_url"
    success "Account found — client_id: ${CLIENT_ID}, identity domain: ${IDENTITY_DOMAIN_URL}"
fi

[[ -z "$IDENTITY_DOMAIN_URL" ]] && fatal \
    "--identity-domain-url is required" \
    "Provide your OCI IAM identity domain URL." \
    "Find it at: OCI Console → Identity & Security → Domains → copy the Domain URL"

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

# 3. OCI CLI configured
info "Checking OCI CLI credentials..."
if ! oci iam region list --output json > /dev/null 2>&1; then
    fatal "OCI CLI credentials are invalid or not configured" \
        "Run: oci setup config" \
        "Your OCI user must have identity domain administrator permissions." \
        "Docs: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"
fi
success "OCI CLI credentials valid"

# 3. Fusion app ID resolves in identity domain
if [[ -n "$FUSION_APP_ID" ]]; then
    info "Verifying Fusion app ID '${FUSION_APP_ID}' exists in identity domain..."
    fusion_app_resp=$(oci identity-domains apps list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "id eq \"${FUSION_APP_ID}\"" \
        --output json 2>/dev/null)
    fusion_app_name=$(echo "$fusion_app_resp" | python3 -c "
import sys,json
apps = json.load(sys.stdin).get('data',{}).get('resources',[])
print(apps[0].get('display-name','') if apps else '')
" 2>/dev/null)
    [[ -z "$fusion_app_name" ]] && fatal \
        "Fusion app ID '${FUSION_APP_ID}' was not found in identity domain '${IDENTITY_DOMAIN_URL}'" \
        "Verify the Application ID at: OCI Console → Domains → Applications → Fusion Apps Cloud Service" \
        "Ensure you are using the hex Application ID, not the OCID."
    FUSION_SCOPE=$(echo "$fusion_app_resp" | python3 -c "
import sys,json
app = json.load(sys.stdin).get('data',{}).get('resources',[])[0]
audience = app.get('audience','')
print(audience if audience.endswith('consumer::all') else audience + 'urn:opc:resource:consumer::all')
" 2>/dev/null)
    success "Fusion app found: '${fusion_app_name}' — scope derived"
fi

# 4. EPM app ID resolves in identity domain
if [[ -n "$EPM_APP_ID" ]]; then
    info "Verifying EPM app ID '${EPM_APP_ID}' exists in identity domain..."
    epm_app_resp=$(oci identity-domains apps list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "id eq \"${EPM_APP_ID}\"" \
        --output json 2>/dev/null)
    epm_app_name=$(echo "$epm_app_resp" | python3 -c "
import sys,json
apps = json.load(sys.stdin).get('data',{}).get('resources',[])
print(apps[0].get('display-name','') if apps else '')
" 2>/dev/null)
    [[ -z "$epm_app_name" ]] && fatal \
        "EPM app ID '${EPM_APP_ID}' was not found in identity domain '${IDENTITY_DOMAIN_URL}'" \
        "Verify the Application ID at: OCI Console → Domains → Applications → your EPM app" \
        "Ensure you are using the hex Application ID, not the OCID."
    EPM_SCOPE=$(echo "$epm_app_resp" | python3 -c "
import sys,json
app = json.load(sys.stdin).get('data',{}).get('resources',[])[0]
audience = app.get('audience','')
print(audience if audience.endswith('consumer::all') else audience + 'urn:opc:resource:consumer::all')
" 2>/dev/null)
    success "EPM app found: '${epm_app_name}' — scope derived"
fi

# 5. Validate Fusion admin credentials + connectivity
if [[ -n "$FUSION_APP_ID" ]]; then
    info "Validating Fusion admin credentials and connectivity..."
    fusion_auth_status=$(curl -s --compressed -o /dev/null -w "%{http_code}" \
        "${FUSION_BASE_URL}/hcmRestApi/scim/Users?count=1" \
        -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" 2>/dev/null)
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

# 6. EPM URL reachable
if [[ -n "$EPM_APP_ID" ]]; then
    info "Checking EPM URL reachability..."
    epm_status=$(curl -s -o /dev/null -w "%{http_code}" \
        "${EPM_BASE_URL}/HyperionPlanning/rest/v3/applications" 2>/dev/null)
    [[ "$epm_status" == "000" ]] && fatal \
        "Cannot reach EPM at '${EPM_BASE_URL}'" \
        "Check that the EPM base URL is correct and reachable from this machine."
    success "EPM URL reachable (HTTP ${epm_status})"
fi

# 7. DD_INTEGRATION_ROLE exists in Fusion and is accessible via API
#    We check the role CODE (the 'name' field in SCIM).
#    The role code must be exactly 'DD_INTEGRATION_ROLE'.
if [[ -n "$FUSION_APP_ID" ]]; then
    info "Checking for role with code 'DD_INTEGRATION_ROLE' in Fusion..."
    info "(The role CODE must be exactly 'DD_INTEGRATION_ROLE')"
    role_check=$(curl -s --compressed \
        "${FUSION_BASE_URL}/hcmRestApi/scim/Roles?filter=name+eq+%22DD_INTEGRATION_ROLE%22" \
        -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
        -H "Accept: application/json" 2>/dev/null)
    role_count=$(echo "$role_check" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('totalResults',0))
" 2>/dev/null)
    if [[ -z "$role_count" || "$role_count" == "0" ]]; then
        fatal "No role with code 'DD_INTEGRATION_ROLE' was found in Fusion or it is not API-assignable" \
            "This custom role must be created in Oracle Fusion Security Console before onboarding." \
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
            "     Setup and Maintenance → Manage Role Provisioning Rules → Add DD_INTEGRATION_ROLE" \
            "     Check 'Requestable' to allow API assignment"
    fi
    DD_INTEGRATION_ROLE_ID=$(echo "$role_check" | python3 -c "
import sys,json; rs=json.load(sys.stdin).get('Resources',[]); print(rs[0].get('id','') if rs else '')
" 2>/dev/null)
    success "'DD_INTEGRATION_ROLE' found and accessible via API"
fi

# 8. Idempotency — check if confidential app already exists
APP_NAME="Datadog Fusion Integration"
info "Checking if '${APP_NAME}' already exists in OCI IAM..."
existing_app=$(oci identity-domains apps list \
    --endpoint "$IDENTITY_DOMAIN_URL" \
    --filter "displayName eq \"${APP_NAME}\"" \
    --output json 2>/dev/null)
existing_app_id=$(echo "$existing_app" | python3 -c "
import sys,json
apps=json.load(sys.stdin).get('data',{}).get('resources',[])
print(apps[0].get('name','') if apps else '')
" 2>/dev/null)

APP_EXISTS=false
if [[ -n "$existing_app_id" ]]; then
    APP_EXISTS=true
    if [[ "$RESUME" == false ]]; then
        echo ""
        echo -e "${YELLOW}${BOLD}  A confidential application named '${APP_NAME}' already exists.${NC}"
        echo -e "  client_id: ${existing_app_id}"
        echo ""
        echo -e "  Options:"
        echo -e "    --resume     Re-use this app and continue provisioning the integration user"
        echo -e "                 (recommended if a previous run was interrupted)"
        echo ""
        exit 0
    fi
    CLIENT_ID="$existing_app_id"
    warn "Existing app found — resuming with client_id: ${CLIENT_ID}"
fi

# 9. Idempotency — check if user already exists
#    For Fusion+EPM: check Fusion SCIM (user was created there)
#    For EPM-only: check OCI IAM directly (user created there instead)
FUSION_USER_EXISTS=false
OCI_IAM_USER_EXISTS=false
if [[ -n "$CLIENT_ID" ]]; then
    if [[ -n "$FUSION_APP_ID" ]]; then
        info "Checking if Fusion user '${CLIENT_ID}' already exists..."
        existing_user=$(curl -s --compressed \
            "${FUSION_BASE_URL}/hcmRestApi/scim/Users?filter=userName+eq+%22${CLIENT_ID}%22" \
            -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
            -H "Accept: application/json" 2>/dev/null)
        existing_user_id=$(echo "$existing_user" | python3 -c "
import sys,json; rs=json.load(sys.stdin).get('Resources',[]); print(rs[0].get('id','') if rs else '')
" 2>/dev/null)
        if [[ -n "$existing_user_id" ]]; then
            FUSION_USER_EXISTS=true
            FUSION_USER_ID="$existing_user_id"
            warn "Fusion user already exists (id: ${FUSION_USER_ID}) — skipping creation"
        fi
    elif [[ -z "$FUSION_APP_ID" ]]; then
        info "Checking if OCI IAM user '${CLIENT_ID}' already exists..."
        existing_oci_user=$(oci identity-domains users list \
            --endpoint "$IDENTITY_DOMAIN_URL" \
            --filter "userName eq \"${CLIENT_ID}\"" \
            --output json 2>/dev/null)
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
    info "Skipping — using existing app (client_id: ${CLIENT_ID})"
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
        "Application was created but client_id could not be retrieved" \
        "Check OCI Console → Domains → Applications → '${APP_NAME}' for the Application ID"

    success "Confidential application created"
    echo ""
    echo -e "  ${BOLD}client_id:${NC}     ${CLIENT_ID}"
    echo -e "  ${BOLD}app_ocid:${NC}      ${APP_OCID}"
    if [[ -n "$CLIENT_SECRET" ]]; then
        echo -e "  ${BOLD}client_secret:${NC} ${CLIENT_SECRET}"
    else
        echo -e "  ${YELLOW}client_secret: retrieve from OCI Console → Applications → '${APP_NAME}' → OAuth Configuration${NC}"
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
            "${_oci_emails_arg[@]}" \
            --output json 2>/dev/null) || fatal \
            "Failed to create OCI IAM user '${CLIENT_ID}'" \
            "Ensure your OCI credentials have permission to create users in the identity domain." \
            "Check: OCI Console → Domains → Administrators"

        OCI_IAM_USER_ID=$(echo "$oci_user_result" | python3 -c "
import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',''))
" 2>/dev/null)
        [[ -z "$OCI_IAM_USER_ID" ]] && fatal \
            "OCI IAM user was created but ID could not be retrieved" \
            "Check OCI Console → Domains → Users for the new user."
        success "OCI IAM user created (id: ${OCI_IAM_USER_ID})"
    fi

fi

# ══════════════════════════════════════════════════════════════════════════════
if [[ -n "$FUSION_APP_ID" ]]; then

    step "STEP 2: CREATE FUSION INTEGRATION USER"

    if [[ "$FUSION_USER_EXISTS" == true ]]; then
        info "Skipping — Fusion user already exists (id: ${FUSION_USER_ID})"
    else
        info "Creating Fusion user with username '${CLIENT_ID}'..."
        _fusion_user_body=$(python3 -c "
import json
body = {
    'schemas': ['urn:scim:schemas:core:2.0:User'],
    'userName': '${CLIENT_ID}',
    'name': {'familyName': 'Datadog Integration'},
    'active': True,
}
email = '${USER_EMAIL:-}'
if email:
    body['emails'] = [{'value': email, 'type': 'work', 'primary': True}]
print(json.dumps(body))
")
        user_response=$(curl -s --compressed -w "|||%{http_code}" \
            -X POST "${FUSION_BASE_URL}/hcmRestApi/scim/Users" \
            -u "${FUSION_ADMIN_USERNAME}:${FUSION_ADMIN_PASSWORD}" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d "$_fusion_user_body" 2>/dev/null)
        user_status="${user_response##*|||}"
        user_body="${user_response%|||*}"

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

    patch_status=$(echo "$patch_result" | tail -1)

    if [[ "$patch_status" != "204" && "$patch_status" != "200" ]]; then
        fatal "Failed to assign DD_INTEGRATION_ROLE (HTTP ${patch_status})" \
            "Verify that 'DD_INTEGRATION_ROLE' is in Fusion Role Provisioning Rules:" \
            "  Setup and Maintenance → Manage Role Provisioning Rules" \
            "The role must be marked as 'Requestable' to be assignable via API."
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
        "Wait a few minutes and re-run with --resume."

    success "OCI IAM user found (id: ${OCI_IAM_USER_ID})"

    # Find EPM Service Administrator role ID
    info "Finding EPM Service Administrator role..."
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
        "Check: OCI Console → Domains → Applications → your EPM app → Application ID"

    success "EPM Service Administrator role found (id: ${SERVICE_ADMIN_ROLE_ID})"

    # Check if grant already exists
    info "Checking if EPM role grant already exists..."
    existing_grant=$(oci identity-domains grants list \
        --endpoint "$IDENTITY_DOMAIN_URL" \
        --filter "grantee.value eq \"${OCI_IAM_USER_ID}\" and app.value eq \"${EPM_APP_ID}\"" \
        --output json 2>/dev/null | python3 -c "
import sys,json
rs=json.load(sys.stdin).get('data',{}).get('resources',[])
print(len(rs))
" 2>/dev/null)

    if [[ "${existing_grant:-0}" -gt 0 ]]; then
        warn "EPM Service Administrator grant already exists — skipping"
    else
        info "Creating EPM Service Administrator grant..."
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

        success "EPM Service Administrator role granted"
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

existing_account_id=$(echo "$accounts_resp" | python3 -c "
import sys,json
data = json.load(sys.stdin).get('data', [])
name = '${ACCOUNT_NAME}'
matched = [a for a in data if a.get('attributes', {}).get('name') == name]
print(matched[0].get('id', '') if matched else '')
" 2>/dev/null)

# Build payload — omit optional fields when values are absent;
# omit secrets entirely when CLIENT_SECRET is empty (PATCH keeps the existing secret).
payload=$(python3 -c "
import json, sys
settings = {
    'client_id':  '${CLIENT_ID}',
    'token_url':  '${TOKEN_URL}',
}
fusion_scope   = '${FUSION_SCOPE:-}'
epm_scope      = '${EPM_SCOPE:-}'
fusion_base    = '${FUSION_BASE_URL:-}'
epm_base       = '${EPM_BASE_URL:-}'
if fusion_scope:   settings['oauth_scope']      = fusion_scope
if fusion_base:    settings['fusion_base_url']  = fusion_base
if epm_scope:      settings['epm_oauth_scope']  = epm_scope
if epm_base:       settings['epm_base_url']     = epm_base
attrs = {'name': '${ACCOUNT_NAME}', 'settings': settings}
print(json.dumps({'data': {'type': 'Account', 'attributes': attrs}}))
" 2>/dev/null)

if [[ -n "$existing_account_id" ]]; then
    info "Account exists — updating (id=${existing_account_id})..."
    dd_patch "/api/v2/web-integrations/oracle-fusion/accounts/${existing_account_id}" "$payload" > /dev/null || fatal \
        "Failed to update Datadog Oracle Fusion account" \
        "Verify DD_APP_KEY have 'integrations_write' permissions."
    success "Datadog Oracle Fusion account updated (id=${existing_account_id})"
else
    info "Creating Datadog Oracle Fusion account '${ACCOUNT_NAME}'..."
    create_resp=$(dd_post "/api/v2/web-integrations/oracle-fusion/accounts" "$payload") || fatal \
        "Failed to create Datadog Oracle Fusion account" \
        "Verify DD_APP_KEY have 'integrations_write' permissions."
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
echo -e "  ${YELLOW}${BOLD}Next steps:${NC}"
echo -e "  1. Enter the client_secret in the Datadog Oracle Fusion integration tile:"
echo -e "     OCI Console → Domains → Applications → '${APP_NAME}' → OAuth Configuration"
echo -e "  2. Allow 1-2 minutes for EPM Access Control to sync before testing"
echo ""
