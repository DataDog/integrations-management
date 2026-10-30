# Oracle Fusion Integration Quickstart

Automates the full Oracle Fusion + EPM integration user onboarding for Datadog.
Creates the OCI IAM confidential application, Fusion integration user,
assigns the required Fusion role, and grants EPM Service Administrator access.

## Prerequisites

- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm#configfile) configured with Identity Domain Administrator permissions, using **either** of these auth methods:
  - **API key** (default): run `oci setup config`. The configured tenancy must match the identity domain you pass to `--identity-domain-url`. Check the `tenancy` value in `~/.oci/config`.
  - **Browser-based session** (for tenants that enforce SSO / restrict API signing keys): run `oci session authenticate` once. The script will detect and reuse the session across runs.
- Python **3.6+**, `oci`, and `openssl` available on your PATH. No Python packages or `curl` are required.
- Datadog API and application keys with `integrations_read` and `integrations_write` permissions

## Usage

```
python3 setup.py [OPTIONS]
```

`setup.sh` remains a compatibility entry point and forwards arguments to Python.
Keep `setup.py` alongside it if downloading the scripts individually. All existing
flags and environment variables are supported. Credentials are never printed;
the JWT private key and certificate are generated in memory via OpenSSL.

Python 3.6 matches the minimum needed by the original Bash script's embedded
EPM password generator (`secrets` was introduced in Python 3.6). The port avoids
`subprocess.run(capture_output=...)` (3.7) and `str.removesuffix` (3.9). CI runs
the full test suite on Python 3.6 as well as the normal CI Python version.
This is compatibility support, not a recommendation to use an end-of-life Python.

### Required Fusion role

Before Fusion onboarding or repair, create a custom role in **Security Console →
Roles → Create Role**, with code **DD_INTEGRATION_ROLE** and category Default.
Under Role Hierarchy, add `ESSMonitor`, `ORA_FND_INTEGRATION_SPECIALIST_JOB`, and
`ORA_FND_INTERNAL_AUDITOR_JOB`, keeping their automatically included sub-roles.
In **Setup and Maintenance → Manage Role Provisioning Rules**, add a mapping
starting today with blank conditions. Add the custom role as an Associated Role,
check **Requestable**, and leave other checkboxes unchecked. Save and Close.
The script verifies this role; it cannot create it through the Fusion API.

### Development and tests

```bash
python3 -m unittest discover -s oracle_fusion/integration_quickstart/tests -v
```

Run this from the repository root. Tests cover input validation, scopes, password
policies, payloads, and mocked fresh Fusion/EPM, add-EPM, and repair flows. They do
not provision cloud resources. An OpenSSL smoke test checks in-memory key and
certificate generation. The Python entry point separates pure helpers from the
`External` effects adapter and the `Onboarding` orchestration. The orchestrator
uses named phases for loading accounts, resolving scopes, checking services,
reconciling apps/users/grants, rotating credentials, and registering with Datadog.
Each phase can be tested independently using the same effects adapter.

Reruns reuse existing apps/users/grants. Repair reasserts app configuration even
when scopes are already present. Existing app secrets and EPM credentials rotate
on reruns; if registration fails after rotation, rerun to complete registration.

## Options

| Option                         | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--identity-domain-url URL`    | OCI IAM identity domain URL (required unless `--account-name` is used)                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `--fusion-app-id ID`           | Hex ID of the Fusion SaaS app in OCI IAM (required for Fusion)                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `--epm-app-id ID`              | Hex ID of the EPM SaaS app in OCI IAM (required for EPM)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `--fusion-base-url URL`        | Fusion environment base URL (required for Fusion; not used with `--account-name`)                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `--epm-base-url URL`           | EPM environment base URL (required for EPM fresh onboarding; optional with `--account-name` if already set on account)                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `--fusion-admin-username USER` | Fusion admin username (required for Fusion; not used with `--account-name`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `--fusion-admin-password PASS` | Fusion admin password (required for Fusion; not used with `--account-name`; not stored)                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `--user-email EMAIL`           | Email address to attach to the created integration user.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `--account-name NAME`          | Name of an existing Datadog Fusion account to add EPM to. Requires `--fusion-app-id` and `--epm-app-id`. Cannot be used with `--identity-domain-url`, `--fusion-base-url`, `--fusion-admin-username`, `--fusion-admin-password`, or `--user-email`.                                                                                                                                                                                                                                                                                        |
| `--fix`                        | Diagnose and repair drift on an existing Datadog Fusion/EPM account named by `--account-name`. Reruns onboarding to recreate missing OCI app scopes, the Fusion/OCI IAM integration user, and EPM grants; always rotates and re-registers the OCI client secret. Requires `--account-name` (and, if the account has Fusion configured, `--fusion-admin-username`/`--fusion-admin-password`, plus `--fusion-app-id` if the account does not already have one on record); `--user-email` is also supported for recreated users. Cannot recover a deleted OCI confidential app — reinstall from scratch in that case (run without `--account-name`). |

## Environment Variables

| Variable     | Description                                                                   |
| ------------ | ----------------------------------------------------------------------------- |
| `DD_API_KEY` | Your Datadog API key                                                          |
| `DD_APP_KEY` | Your Datadog application key                                                  |
| `DD_SITE`    | Your Datadog site (e.g. `datadoghq.com`, `datadoghq.eu`, `us3.datadoghq.com`) |

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

**Repair an existing, unhealthy account:**

```bash
export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
export DD_SITE=datadoghq.com
./setup.sh \
  --account-name "My Fusion Account" \
  --fusion-admin-username admin@example.com \
  --fusion-admin-password mypassword \
  --fix
```

## Browser-based authentication

Some OCI identity domains enforce SSO via the browser and restrict traditional API signing keys. In that case, the script can authenticate the OCI CLI with a browser-based session token instead of an API key.

The script automatically:

1. Uses the API key in `~/.oci/config` if it works.
2. Otherwise reuses the script's own `datadog-fusion` browser session profile if it's present and valid (so re-runs don't re-prompt). The script only ever reuses the profile it creates — it never touches session profiles you set up for other purposes.
3. If neither works, prompts **"Use browser-based authentication? [y/N]"** and, on `y`, runs `oci session authenticate` to open your browser.

If you decline browser-based auth, you must configure local OCI CLI credentials and re-run the script:

```bash
oci setup config
```

Your OCI user must have Identity Domain Administrator permissions. See the [OCI CLI install/setup docs](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm#configfile) for details.

### Notes

- Browser sessions persist in `~/.oci/config` as a profile with a `security_token_file` entry. The script creates and reuses a profile named `datadog-fusion`, so you only authenticate in the browser once per session lifetime.
- Session tokens expire after about an hour and are refreshable up to 24 hours. The script refreshes an expired session automatically; if it can't, it will prompt you to re-authenticate.
- Browser-based auth grants the same permissions as an API key for the same user — it is a way to authenticate when API keys are unavailable, not a way to escalate privileges. The signed-in user must still have Identity Domain Administrator access to the target domain.
- For headless/CI runs without a browser, run `oci session authenticate` on a machine with a browser, then `oci session export` / `oci session import` to copy the session.
