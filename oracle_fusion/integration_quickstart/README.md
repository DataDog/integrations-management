# Oracle Fusion Integration Quickstart

Automates the full Oracle Fusion + EPM integration user onboarding for Datadog.
Creates the OCI IAM confidential application, Fusion integration user,
assigns the required Fusion role, and grants EPM Service Administrator access.

## Prerequisites

- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) configured with Identity Domain Administrator permissions
- `python3` and `curl` available on your PATH
- Datadog API and application keys with `integrations_read` and `integrations_write` permissions

## Usage

```
./setup.sh [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--identity-domain-url URL` | OCI IAM identity domain URL (required unless `--account-name` is used) |
| `--fusion-app-id ID` | Hex ID of the Fusion SaaS app in OCI IAM (required for Fusion) |
| `--epm-app-id ID` | Hex ID of the EPM SaaS app in OCI IAM (required for EPM) |
| `--fusion-base-url URL` | Fusion environment base URL (required for Fusion) |
| `--epm-base-url URL` | EPM environment base URL (required for EPM) |
| `--fusion-admin-username USER` | Fusion admin username (required for Fusion) |
| `--fusion-admin-password PASS` | Fusion admin password (required for Fusion, not stored) |
| `--user-email EMAIL` | Email address to attach to the created integration user. Required by some OCI identity domains. |
| `--account-name NAME` | Datadog integration account name. If a matching account already exists, its credentials are fetched and the account is updated. When `--identity-domain-url` is omitted, it is derived from the existing account's `token_url` (add-EPM-to-existing-account flow). |
| `--resume` | Re-use existing confidential app if found, skip completed steps |
| `--epm-only` | Skip Fusion user/role steps, only provision EPM access |
| `--fusion-only` | Skip EPM steps, only provision Fusion access |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DD_API_KEY` | Your Datadog API key |
| `DD_APP_KEY` | Your Datadog application key |
| `DD_SITE` | Your Datadog site (e.g. `datadoghq.com`, `datadoghq.eu`, `us3.datadoghq.com`) |

## Examples

**Full Fusion + EPM onboarding:**

```bash
export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
export DD_SITE=datadoghq.com
./setup.sh \
  --identity-domain-url https://idcs-XXXX.identity.oraclecloud.com \
  --fusion-app-id 47196679097c447486306f0023f5ef4d \
  --epm-app-id 1fbd4f1bc91a4ffda592776a9841493f \
  --fusion-base-url https://icjnjb.fa.ocs.oraclecloud.com \
  --epm-base-url https://epmprod-xx.epm.us-ashburn-1.ocs.oraclecloud.com \
  --fusion-admin-username admin@company.com \
  --fusion-admin-password mypassword
```

**Add EPM to an existing Fusion account:**

```bash
export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
./setup.sh \
  --account-name "My Fusion Account" \
  --epm-only \
  --epm-app-id 1fbd4f1bc91a4ffda592776a9841493f \
  --epm-base-url https://epmprod-xx.epm.us-ashburn-1.ocs.oraclecloud.com
```
