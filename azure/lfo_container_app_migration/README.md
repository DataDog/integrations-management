# Overview
This project migrates an existing Azure Log Forwarding Orchestration installation from a
Function Apps control plane to a Container App Jobs control plane, in place.

For end users, the produced executable will run in an [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/classic?tabs=azurecli) in bash mode.

For development, you can run the script locally (assuming you have Azure CLI setup).

During final testing, you should upload the executable into Azure Cloud Shell and run it there.

The migration runs in phases (discovery, Container App Job creation, role assignment,
enablement/cutover, cleanup). Each step has a corresponding rollback; if a step fails, its
rollback runs, then the rollback actions of preceding steps run in reverse order. The old
Function Apps and App Service Plan are only deleted after the new Container App Jobs are
verified to be running successfully. The script is idempotent and can be re-run safely.

# Development
### Dev Setup
See instructions in main `azure` folder

### Testing
Run all tests from the `azure` folder:
```bash
python -m pytest caj_migration/tests/ --tb=short
```

### Build/Ship
Run from the `azure` folder:
Zip app into a single executable file `dist/azure_lfo_container_app_migration.pyz`

```bash
caj_migration/build.sh
```

### Execution
Usage
```bash
usage: azure_lfo_container_app_migration.pyz [-h] [--control-plane-ids CONTROL_PLANE_IDS]
                               [--yes]
                               [--log-level {DEBUG,INFO,WARNING,ERROR}]

Migrate an Azure Log Forwarding Orchestration control plane from Function Apps to Container App Jobs

options:
  -h, --help            show this help message and exit
  --control-plane-ids CONTROL_PLANE_IDS
                        Comma-separated list of specific control plane IDs to
                        migrate. Default: auto-discover every eligible
                        Function-App-based installation in the tenant.
  --yes                 Don't prompt for confirmation before migrating each
                        discovered installation
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Set the log level (default: INFO)
```

With no arguments, the script discovers every Function-App-based LFO installation the
current Azure login has access to and prompts for confirmation before migrating each one.
Pass `--control-plane-ids` to target specific installations directly (skips discovery-wide
confirmation for those), or `--yes` to skip confirmation prompts entirely.
