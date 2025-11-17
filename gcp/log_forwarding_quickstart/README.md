# Overview

This project sets up **Datadog's GCP log forwarding** for new customers. It supports:

- Log forwarding from GCP to Datadog using Dataflow
- Pub/Sub topic and subscription creation
- Secret Manager configuration for API keys
- Log sink creation for projects and folders
- Dataflow job deployment with optional Prime support

It is designed to work in conjunction with the **Quickstart onboarding UI**, which can be found [here](https://app.datadoghq.com/integrations/google-cloud-platform/logs) under the "Quickstart" tab.

The produced executable is intended to run in a [Google Cloud Shell](https://cloud.google.com/shell/docs/using-cloud-shell) environment.

For development purposes, the script can also be run locally (assuming you have the [gcloud CLI](https://cloud.google.com/sdk/docs/install) set up).

During final testing, upload the executable to Google Cloud Shell and run it there.

---

# Development

### Dev Setup

See instructions in the main `gcp/` folder.

### Testing

Run all tests from the `log_forwarding_quickstart` folder:

```bash
PYTHONPATH=src:../shared/src python -m pytest tests/ --tb=short
```

Or run tests with verbose output:

```bash
PYTHONPATH=src:../shared/src python -m pytest tests/ -v
```

### Build / Ship

From the `gcp/` folder, run:

```bash
bash log_forwarding_quickstart/build.sh
```

# Execution

To run log forwarding quickstart, you must first open the Quickstart onboarding UI, which can be found [here](https://app.datadoghq.com/integrations/google-cloud-platform/logs) under "Quickstart".

At the top of this page, you will see a "setup script" snippet. Copy that snippet into Google Cloud Shell and run it.

Once this command is run, the setup script will connect to Datadog and begin reporting back to the onboarding UI, where you will continue the setup process.

