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
| `--user-email EMAIL` | Email address to attach to the created integration user. Only include if required by legacy identity domain. |
| `--account-name NAME` | Datadog integration account name. If a matching account already exists, its credentials are fetched and the account is updated. Requires both `--fusion-app-id` and `--epm-app-id` so OAuth scopes on the confidential app are updated correctly for both products. |
| `--confidential-application-id ID` | Application ID of an existing confidential app. Only required when resuming and your app is not named "Datadog Fusion Integration". |
| `--resume` | Re-use existing confidential app if found, skip completed steps |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DD_APP_KEY` | Your Datadog application key |
| `DD_SITE` | Your Datadog site (e.g. `datadoghq.com`, `datadoghq.eu`, `us3.datadoghq.com`) |

## Examples

**Full Fusion + EPM onboarding:**

```bash
export DD_APP_KEY=<your-app-key>
export DD_SITE=datadoghq.com
./setup.sh \
  --identity-domain-url https://idcs-abc123def456.identity.oraclecloud.com \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --epm-app-id b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5 \
  --fusion-base-url https://your-fusion-env.fa.ocs.oraclecloud.com \
  --epm-base-url https://your-epm-env.epm.us-ashburn-1.ocs.oraclecloud.com \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password mypassword
```

**Resume an interrupted run:**

If the script fails partway through, re-run with `--resume` to skip the confidential app creation and continue from where it left off:

```bash
export DD_APP_KEY=<your-app-key>
./setup.sh \
  --identity-domain-url https://idcs-abc123def456.identity.oraclecloud.com \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --fusion-base-url https://your-fusion-env.fa.ocs.oraclecloud.com \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password mypassword \
  --resume
```

**Add EPM to an existing Fusion account:**

```bash
export DD_APP_KEY=<your-app-key>
./setup.sh \
  --account-name "My Fusion Account" \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --fusion-base-url https://your-fusion-env.fa.ocs.oraclecloud.com \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password '<your-admin-password>' \
  --epm-app-id b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5 \
  --epm-base-url https://your-epm-env.epm.us-ashburn-1.ocs.oraclecloud.com
```

**Add Fusion to an existing EPM account:**

```bash
export DD_APP_KEY=<your-app-key>
./setup.sh \
  --account-name "My EPM Account" \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --fusion-base-url https://your-fusion-env.fa.us2.oraclecloud.com \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password '<your-admin-password>' \
  --epm-app-id b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5 \
  --epm-base-url https://your-epm-env.epm.us-ashburn-1.ocs.oraclecloud.com
```
