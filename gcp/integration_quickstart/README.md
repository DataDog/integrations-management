# Overview

This project sets up **Datadog's GCP integration** for new customers. It supports:

- Metric Collection
- Resource Collection
- Additional integration features

It is designed to work in conjunction with the **Quickstart onboarding UI**, which can be found [here](https://app.datadoghq.com/integrations/google-cloud-platform/add) under the "Quickstart" tab.

The produced executable is intended to run in a [Google Cloud Shell](https://cloud.google.com/shell/docs/using-cloud-shell) environment.

For development purposes, the script can also be run locally (assuming you have the [gcloud CLI](https://cloud.google.com/sdk/docs/install) set up).

During final testing, upload the executable to Google Cloud Shell and run it there.

---

# Development

### Dev Setup

See instructions in the main `gcp/` folder.

### Testing

Run all tests from the `integration_quickstart` folder:

```bash
PYTHONPATH=src:../shared/src:../agentless/src python -m pytest tests/ --tb=short
```

### Build / Ship

From the `gcp/` folder, run:

```bash
bash integration_quickstart/build.sh
```

# Execution

To run integration quickstart, you must first open the Quickstart onboarding UI, which can be found [here](https://app.datadoghq.com/integrations/google-cloud-platform/add) under "Quickstart".

At the top of this page, you will see a "setup script" snippet. Copy that snippet into Google Cloud Shell and run it.

Once this command is run, the setup script will connect to Datadog and begin reporting back to the onboarding UI, where you will continue the setup process.

### Optional: Agentless Scanning

If any of the following environment variables is set, the script also deploys [Agentless Scanning](../agentless/README.md) once the integration is set up. Inputs and credentials are validated up front, before any integration resources are created. If none is set, the flow is unchanged.

| Variable | Description |
|----------|-------------|
| `AGENTLESS_WORKFLOW_ID` | Workflow ID for the `gcp-agentless-setup` workflow (separate from `WORKFLOW_ID`) |
| `SCANNER_PROJECT` | GCP project where the scanner will be deployed |
| `SCANNER_REGIONS` | Comma-separated list of GCP regions (max 4) |
| `PROJECTS_TO_SCAN` | Comma-separated list of GCP projects to scan |
| `TF_STATE_BUCKET` | Optional custom GCS bucket for Terraform state |

`DD_API_KEY` (which must have Remote Configuration enabled), `DD_APP_KEY`, and `DD_SITE` are shared with the integration setup. If the agentless deploy fails, the integration is kept and the script exits with a non-zero code.
