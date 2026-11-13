# Overview
This script migrates an existing Datadog Azure Automated Log Forwarding installation from a Function App control plane to a Container App Jobs control plane.

New installations have used Container App Jobs since August 3, 2026. Only installations created before that date need this migration. Updating an installation with the installer does not migrate it.

Log forwarders are not changed. The new control plane keeps the existing configuration: monitored subscriptions, Datadog API key and site, resource tag filters, PII scrubber rules, telemetry setting, and log level.

# Prerequisites
The migration creates role assignments on each monitored subscription and on the control plane resource group. You need one of these roles on the control plane subscription and on every monitored subscription: Owner, User Access Administrator, or Role Based Access Control Administrator. Without it, the migration fails partway and rolls back.

# Usage
Run the script in an [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/classic?tabs=azurecli) in bash mode.

1. Download the script and run a dry run, which is the default. The dry run shows the settings that will be copied and every step the migration will run, without changing any Azure resources. It does not check that you have the roles listed in [Prerequisites](#prerequisites).
   ```bash
   curl -sSL -o azure_lfo_container_app_migration.pyz \
     https://raw.githubusercontent.com/DataDog/integrations-management/main/azure/lfo_container_app_migration/dist/azure_lfo_container_app_migration.pyz
   python3 azure_lfo_container_app_migration.pyz
   ```

2. Run the migration:
   ```bash
   python3 azure_lfo_container_app_migration.pyz --dry-run=false
   ```

By default, the script finds every Function App installation in the subscriptions you have access to. With `--dry-run=false`, it asks for confirmation before migrating each one.

Optional flags (output of `--help`):
```
usage: azure_lfo_container_app_migration.pyz [-h]
                                             [--control-plane-ids CONTROL_PLANE_IDS]
                                             [--yes] [--dry-run [true|false]]
                                             [--no-dry-run]
                                             [--log-level {DEBUG,INFO,WARNING,ERROR}]

options:
  -h, --help            show this help message and exit
  --control-plane-ids CONTROL_PLANE_IDS
                        Comma-separated list of specific control plane IDs to migrate. Default:
                        auto-discover every eligible Function-App-based installation in the
                        tenant.
  --yes                 With --dry-run=false, don't prompt for confirmation before migrating each
                        discovered installation
  --dry-run [true|false]
                        Dry run (the default): show the settings that would be copied and every
                        step the migration would run, without changing any Azure resources. Does
                        not check that you have the permissions the migration needs. The Azure CLI
                        'resource-graph' extension is still installed if missing. Pass --dry-
                        run=false (or --no-dry-run) to perform the migration.
  --no-dry-run          Perform the migration. Same as --dry-run=false
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Set the log level (default: INFO)
```

# What the script does
For each control plane:
1. Creates the resources, diagnostic settings, and scaling task Container App Jobs, paused.
2. Assigns the roles the new jobs need, and the Container Apps Jobs Contributor role to the deployer. Creates the control plane resource group in any monitored subscription that doesn't have one.
3. Pauses the deployer job and stops the Function Apps.
4. Enables the new jobs, switches the deployer to the Container App Jobs image, and resumes the deployer.
5. Deletes the Function Apps and their App Service plan, deletes the control plane cache file share, and removes the deployer's Website Contributor role.

If a step in 1–4 fails, the script attempts to roll back the completed steps for that installation and then stops. Remaining installations are not migrated, and resource groups created in step 2 are kept. Check the log for any rollback errors. If a step in 5 fails, the migration is still complete. The script lists the resources to delete manually.

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
