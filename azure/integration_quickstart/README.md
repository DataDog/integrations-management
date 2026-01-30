# Overview

This project sets up Datadog's Azure integration for new customers or new scopes. It is designed to work in conjunction with the Quickstart onboarding UI, which can be found [here](https://app.datadoghq.com/integrations/azure/add) under "Quickstart".

## Quickstart Variants

This project builds two quickstart executables:

### Full Quickstart (`azure_integration_quickstart.pyz`)
- **Purpose**: Complete Azure integration setup
- **Sets up**:
  - Azure App Registration with Monitoring Reader role for Metric Collection, Resource Collection, and more
  - (Optional) Log Forwarder for Log Collection
  - (Optional) Datadog Agent on VMs

### LFO-Only Quickstart (`azure_lfo_quickstart.pyz`)
- **Purpose**: Log Forwarder deployment only
- **Sets up**:
  - Log Forwarder for Log Collection

## Environment

For end users, the produced executables will run in an [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/get-started/classic?tabs=azurecli) in bash mode.

For development, you can run the script locally (assuming you have Azure CLI setup).

During final testing, you should upload the executable into Azure Cloud Shell and run it there.

# Development

### Dev Setup

See instructions in main `azure` folder

### Testing
Run all tests from the `azure` folder:
```bash python -m pytest integration_quickstart/tests/ --tb=short```

### Build/Ship

Run from the `azure` folder:
```bash integration_quickstart/build.sh```

This builds both quickstart executables:
- `integration_quickstart/dist/azure_integration_quickstart.pyz` (full quickstart)
- `integration_quickstart/dist/azure_lfo_quickstart.pyz` (LFO-only quickstart)

# Execution

To run integration quickstart, you must first open the Quickstart onboarding UI, which can be found [here](https://app.datadoghq.com/integrations/azure/add) under "Quickstart".

At the top of this page, you will see a "setup script" snippet. Copy that snippet into Azure Cloud Shell in bash mode and execute it.

Once you run this command, the setup script will connect to Datadog and begin reporting back to the onboarding UI, where you will continue the setup process.
