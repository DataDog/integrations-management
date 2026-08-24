# Oracle Fusion Integration Quickstart

Automates the full Oracle Fusion + EPM integration user onboarding for Datadog.
Creates the OCI IAM confidential application, Fusion integration user,
assigns the required Fusion role, and grants EPM Service Administrator access.

## Prerequisites

- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) configured with Identity Domain Administrator permissions, using **either** of these auth methods:
  - **API key** (default): run `oci setup config`. The configured tenancy must match the identity domain you pass to `--identity-domain-url`. Check the `tenancy` value in `~/.oci/config`.
  - **Browser-based session** (for tenants that enforce SSO / restrict API signing keys): run `oci session authenticate` once. The script will detect and reuse the session across runs.
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
| `--oci-auth MODE` | How to authenticate the OCI CLI: `api_key`, `session`, or `auto` (default: `auto`). See "Browser-based authentication" below. |

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

## Browser-based authentication

Some OCI identity domains enforce SSO via the browser and restrict traditional API signing keys. In that case, the script can authenticate the OCI CLI with a browser-based session token instead of an API key.

By default (`--oci-auth auto`), the script:

1. Reuses an existing valid browser session if one is present in `~/.oci/config` (so re-runs don't re-prompt).
2. Otherwise falls back to the API key in `~/.oci/config`.
3. If neither works, prompts **"Use browser-based authentication? [y/N]"** and, on `y`, runs `oci session authenticate` to open your browser.

To force a specific method:

```bash
./setup.sh --oci-auth session ...   # browser-based session only
./setup.sh --oci-auth api_key ...   # API key only
```

### Notes

- Browser sessions persist in `~/.oci/config` as a profile with a `security_token_file` entry. The script detects and reuses them, so you only authenticate in the browser once per session lifetime.
- Session tokens expire after about an hour and are refreshable up to 24 hours. The script refreshes an expired session automatically; if it can't, it will prompt you to re-authenticate.
- Browser-based auth grants the same permissions as an API key for the same user — it is a way to authenticate when API keys are unavailable, not a way to escalate privileges. The signed-in user must still have Identity Domain Administrator access to the target domain.
- For headless/CI runs without a browser, run `oci session authenticate` on a machine with a browser, then `oci session export` / `oci session import` to copy the session. Use `--oci-auth session` to skip the interactive prompt.

