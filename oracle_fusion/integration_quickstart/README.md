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
| `--fusion-base-url URL` | Fusion environment base URL (required for Fusion; not used with `--account-name`) |
| `--epm-base-url URL` | EPM environment base URL (required for EPM fresh onboarding; optional with `--account-name` if already set on account) |
| `--fusion-admin-username USER` | Fusion admin username (required for Fusion; not used with `--account-name`) |
| `--fusion-admin-password PASS` | Fusion admin password (required for Fusion; not used with `--account-name`; not stored) |
| `--user-email EMAIL` | Email address to attach to the created integration user. |
| `--account-name NAME` | Name of an existing Datadog Fusion account to add EPM to. Requires `--fusion-app-id` and `--epm-app-id`. Cannot be used with `--identity-domain-url`, `--fusion-base-url`, `--fusion-admin-username`, `--fusion-admin-password`, or `--user-email`. |

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
  --identity-domain-url https://idcs-abc123def456.identity.oraclecloud.com \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --epm-app-id b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5 \
  --fusion-base-url https://your-fusion-env.fa.ocs.oraclecloud.com \
  --epm-base-url https://your-epm-env.epm.us-ashburn-1.ocs.oraclecloud.com \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password mypassword
```

**Resume an interrupted run:**

If the script fails partway through, simply re-run it with the same arguments — it automatically detects and reuses any existing confidential app, integration user, and EPM grants, skipping steps that are already complete.

**Add EPM to an existing Fusion account:**

```bash
export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
export DD_SITE=datadoghq.com
./setup.sh \
  --account-name "My Fusion Account" \
  --fusion-app-id a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4 \
  --epm-app-id b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5 \
  --epm-base-url https://your-epm-env.epm.us-ashburn-1.ocs.oraclecloud.com
```

