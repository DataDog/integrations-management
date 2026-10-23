# Overview

This project repairs a broken **Datadog GCP integration** by re-applying the
required IAM roles and the Datadog STS delegate permission to an existing
service account, without re-running the full `integration_quickstart` setup.

The produced executable is intended to run in a [Google Cloud Shell](https://cloud.google.com/shell/docs/using-cloud-shell) environment.

For development purposes, the script can also be run locally (assuming you have the [gcloud CLI](https://cloud.google.com/sdk/docs/install) set up).

During final testing, upload the executable to Google Cloud Shell and run it there.

---

# Development

### Dev Setup

See instructions in the main `gcp/` folder.

### Testing

Run all tests from the `issue_resolver` folder:

```bash
PYTHONPATH=src:../shared/src python -m pytest tests/ --tb=short
```

### Build / Ship

From the `gcp/` folder, run:

```bash
bash issue_resolver/build.sh
```

# Execution

The tool supports two invocation modes.

### UI mode

When a "Fix permissions" action is triggered from the Datadog UI, it generates
a Cloud Shell snippet that sets `DD_API_KEY`, `DD_APP_KEY`, `DD_SITE`,
`WORKFLOW_ID`, and `ACCOUNT_EMAIL` (the service account to repair), then downloads and
runs `gcp_issue_resolver.pyz`. With `WORKFLOW_ID` set, the tool waits for the
user to select which project(s) to repair via the Datadog backend (workflow
type `gcp-permission-repair`) and reports progress back the same way
`integration_quickstart` does.

### CLI mode

Support engineers can run the tool directly against a specific service account
and one or more projects, without a workflow ID:

```bash
DD_API_KEY=... DD_APP_KEY=... DD_SITE=... \
  python -m gcp_issue_resolver.main <email> <project_id> [<project_id> ...]
```
