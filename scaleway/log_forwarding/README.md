# Scaleway Log Forwarding Setup

Sets up log forwarding from Scaleway to Datadog via Cockpit native exports and an optional audit trail OTel collector. Full configuration reference and all available environment variables are documented in the script header of `setup-logs.sh`.

## Quick start

```bash
export DD_API_KEY=...
export DD_APP_KEY=...
export DD_SITE=datadoghq.com
bash setup-logs.sh
```

Scaleway credentials are read from your `scw` CLI config. Run `scw init` if you haven't already.

## Teardown

```bash
bash setup-logs.sh --teardown
```

The script scans for resources, prints what it found, and asks for confirmation before deleting anything. Resources removed:

- **Cockpit log exporters** named `datadog-logs-<DD_SITE>` across all configured regions
- **Audit trail Instance** tagged `datadog-audit-trail` (and its volumes and IP)
- **Datadog integration account** for the project

**IAM not included** — the `datadog-integration` IAM application and policy are shared at the organization level and are not removed automatically. Delete them manually from the Scaleway Console (IAM → Applications) if you no longer need them.

Pass `--yes` to skip the confirmation prompt for automation:

```bash
bash setup-logs.sh --teardown --yes
```
