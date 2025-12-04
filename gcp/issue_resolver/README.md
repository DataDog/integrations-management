# Overview

This project provides **Datadog's GCP issue resolver** functionality for customers. It supports:

- Automated issue detection and resolution
- GCP resource configuration checks
- Integration health monitoring
- Diagnostic reporting

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
python -m pytest tests/ --tb=short
```

### Build / Ship

From the `gcp/` folder, run:

```bash
bash issue_resolver/build.sh
```

# Execution

To run issue resolver, you must first open the Quickstart onboarding UI, which can be found [here](https://app.datadoghq.com/integrations/google-cloud-platform/add) under "Issue Resolver".

At the top of this page, you will see a "setup script" snippet. Copy that snippet into Google Cloud Shell and run it.

Once this command is run, the setup script will connect to Datadog and begin reporting back to the onboarding UI, where you will continue the issue resolution process.


