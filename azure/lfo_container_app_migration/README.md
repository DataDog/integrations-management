# Overview
This script migrates an existing Datadog Azure Automated Log Forwarding installation from a Function App control plane to a Container App Jobs control plane.

New installations have used Container App Jobs since August 3, 2026. Only installations created before that date need this migration. Updating an installation with the installer does not migrate it.

Log forwarders are not changed. The new control plane keeps the existing configuration: monitored subscriptions, Datadog API key and site, resource tag filters, PII scrubber rules, and telemetry setting.

# Usage
Run the script in an [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/classic?tabs=azurecli) in bash mode.

```bash
curl -sSL -o azure_lfo_container_app_migration.pyz \
  https://raw.githubusercontent.com/DataDog/integrations-management/main/azure/lfo_container_app_migration/dist/azure_lfo_container_app_migration.pyz
python3 azure_lfo_container_app_migration.pyz
```

By default, the script finds every Function App installation in the tenant and asks for confirmation before migrating each one.

```bash
usage:
./azure_lfo_container_app_migration.pyz [-h]
  [--control-plane-ids CONTROL_PLANE_IDS] \
  [--yes] \
  [--log-level {DEBUG,INFO,WARNING,ERROR}]

options:
  -h, --help            show this help message and exit
  --control-plane-ids CONTROL_PLANE_IDS
                        Comma-separated list of specific control plane IDs to migrate.
                        Default: auto-discover every eligible Function-App-based installation in the tenant.
  --yes                 Don't prompt for confirmation before migrating each discovered installation
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Set the log level (default: INFO)
```

# What the script does
For each control plane:
1. Creates the resources, diagnostic settings, and scaling task Container App Jobs, paused.
2. Assigns the roles the new jobs need, and the Container Apps Jobs Contributor role to the deployer.
3. Pauses the deployer job and stops the Function Apps.
4. Enables the new jobs and switches the deployer to the Container App Jobs image.
5. Deletes the Function Apps and their App Service plan, deletes the control plane cache file share, and removes the deployer's Website Contributor role.

If a step in 1–4 fails, the completed steps are rolled back and the Function App control plane keeps running. If a step in 5 fails, the migration is still complete. The script lists the resources to delete manually.

# Development
### Testing
Run all tests from the `azure` folder:
```bash
python -m pytest lfo_container_app_migration/tests/ --tb=short
```

### Build/Ship
Run from the `azure` folder to build `dist/azure_lfo_container_app_migration.pyz`:
```bash
lfo_container_app_migration/build.sh
```
