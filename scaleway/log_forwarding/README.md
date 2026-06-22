# Scaleway Log Forwarding Setup

Sets up log forwarding from Scaleway to Datadog via Cockpit native exports and an optional audit trail OTel collector.

## Quick start

```bash
export DD_API_KEY=...
export DD_APP_KEY=...
export DD_SITE=datadoghq.com
bash setup-logs.sh
```

Scaleway credentials are read from your `scw` CLI config. Run `scw init` if you haven't already.

## What the script does

1. **IAM Application** — creates a least-privilege `datadog-integration` IAM Application with an ObservabilityFullAccess policy and generates an API key pair. Idempotent — reuses the app if it already exists.
2. **Cockpit log exporters** — configures native Scaleway Cockpit exporters to push product logs to Datadog across all projects and regions. No agent required.
3. **Audit trail collector** *(optional, `SCW_AUDIT_TRAIL_ENABLED=true`)* — builds and deploys an OpenTelemetry Collector with the `scwaudittrail` receiver to forward org-wide IAM/audit events to Datadog Logs.
4. **Datadog account registration** — creates or updates the Scaleway integration account in Datadog with the provisioned credentials.

## Prerequisites

| Tool | When needed |
|---|---|
| `scw` CLI | Always. The script installs it on Linux and macOS if missing; [install manually](https://github.com/scaleway/scaleway-cli) on other platforms. Credentials must have IAM Manager or Org Owner permissions. |
| `curl`, `jq` | Always. |
| `docker`, `ssh`, `scp` | Audit trail collection only. Docker must be running on the machine executing the script; the OTel Collector binary is built locally before being deployed to the instance. |

## Configuration

| Variable | Description | Default |
|---|---|---|
| `DD_API_KEY` | Datadog API key | required |
| `DD_APP_KEY` | Datadog application key | required |
| `DD_SITE` | Datadog site (e.g. `datadoghq.com`, `datadoghq.eu`, `us3.datadoghq.com`) | required |
| `SCW_SECRET_KEY` | Scaleway IAM secret key | from `scw` config |
| `SCW_ACCESS_KEY` | Scaleway IAM access key | from `scw` config |
| `SCW_PROJECT_ID` | Scaleway project to configure exports for | from `scw` config |
| `SCALEWAY_REGIONS` | Comma-separated Cockpit regions | `fr-par,nl-ams,pl-waw` |
| `SCALEWAY_PRODUCTS` | Comma-separated products to export, or `all` | `all` |
| `SCW_AUDIT_TRAIL_ENABLED` | Enable audit trail collector | `true` |
| `SCW_INSTANCE_IP` | IP of an existing instance to deploy the collector to (skips provisioning) | auto-provision |
| `PROVISION_INSTANCE` | `auto` (prompt), `true` (skip prompt), `false` (skip audit trail entirely) | `auto` |
| `SCW_AUDIT_INSTANCE_TYPE` | Commercial type for the provisioned instance | `DEV1-S` (~€6.34/month) |
| `SCW_AUDIT_INSTANCE_ZONE` | Zone for the provisioned instance | `${SCW_REGION}-1` |
| `SCW_AUDIT_INSTANCE_IMAGE` | Image for the provisioned instance | `ubuntu_jammy` |
| `SCW_INSTANCE_USER` | SSH user for the instance | `root` |
| `SCW_ACCOUNT_NAME` | Name for the Datadog integration account | `SCW_PROJECT_ID` |

For private-subnet instances, configure `ProxyJump` in `~/.ssh/config`. See [Scaleway SSH bastion docs](https://www.scaleway.com/en/docs/public-gateways/how-to/use-ssh-bastion/).

## Teardown

```bash
bash setup-logs.sh --teardown
```

The script scans for resources, prints what it found, and asks for confirmation before deleting anything. Resources removed:

- **Cockpit log exporters** named `datadog-logs-<DD_SITE>` across all configured regions
- **Audit trail Instance** tagged `datadog-audit-trail` (and its volumes and IP)
- **Datadog integration account** for the project

**IAM not included** — the `datadog-integration` IAM application and policy are org-scoped and are not removed automatically. Delete them manually from the Scaleway Console (IAM → Applications) if you no longer need them.

Pass `--yes` to skip the confirmation prompt for automation:

```bash
bash setup-logs.sh --teardown --yes
```

## Dry run

```bash
bash setup-logs.sh --dry-run
```

Prints every API call without executing it. All env vars must still be set, but fake values work:

```bash
SCW_SECRET_KEY=x SCW_ACCESS_KEY=x SCW_PROJECT_ID=x \
DD_API_KEY=x DD_APP_KEY=x DD_SITE=datadoghq.com \
bash setup-logs.sh --dry-run
```
