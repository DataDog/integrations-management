# GCP Agentless Scanner Setup

This script automates the deployment of Datadog Agentless Scanner on GCP using Terraform.

## Prerequisites

- Google Cloud Shell or a machine with:
  - `gcloud` CLI installed and authenticated
  - `terraform` CLI installed (>= 1.0)
- GCP projects with appropriate permissions:
  - `roles/owner` or equivalent on the scanner project
  - `roles/iam.serviceAccountCreator` on scanned projects

## Usage

Run the script with environment variables:

```bash
DD_API_KEY="your-api-key" \
DD_APP_KEY="your-app-key" \
DD_SITE="datadoghq.com" \
SCANNER_PROJECT="my-scanner-project" \
SCANNER_REGIONS="us-central1" \
PROJECTS_TO_SCAN="project1,project2,project3" \
python gcp_agentless_setup.pyz
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DD_API_KEY` | Yes | Datadog API key with Remote Configuration enabled |
| `DD_APP_KEY` | Yes | Datadog Application key |
| `DD_SITE` | Yes | Datadog site (e.g., `datadoghq.com`, `datadoghq.eu`) |
| `SCANNER_PROJECT` | Yes | GCP project where the scanner VM will be deployed |
| `SCANNER_REGIONS` | Yes | Comma-separated list of GCP regions (max 4) for scanners (e.g., `us-central1` or `us-central1,europe-west1`) |
| `PROJECTS_TO_SCAN` | Yes | Comma-separated list of GCP projects to scan |
| `TF_STATE_BUCKET` | No | Custom GCS bucket for Terraform state (see below) |

### Terraform State Storage

Terraform state is stored in a GCS bucket to ensure persistence across runs and enable future updates or teardown.

**Default behavior:** A bucket named `datadog-agentless-tfstate-{scanner_project}` is automatically created in the scanner project. If the bucket already exists (e.g., from a previous run), it is reused.

**Custom bucket:** Set `TF_STATE_BUCKET` to use your own bucket:
```bash
TF_STATE_BUCKET="my-existing-bucket" \
SCANNER_PROJECT="my-project" \
# ... other variables ...
python gcp_agentless_setup.pyz
```
The custom bucket must already exist; the script will not create it.

## What it does

1. **Validates prerequisites** - Checks GCP authentication and project access
2. **Enables required APIs** - Enables Compute, IAM, Secret Manager, and Storage APIs
3. **Creates Terraform state bucket** - Creates a GCS bucket for Terraform state
4. **Generates Terraform configuration** - Creates `main.tf` with scanner and service account resources
5. **Runs Terraform** - Executes `terraform init` and `terraform apply`

## Resources Created

- **Scanner Project:**
  - VPC network with Cloud NAT
  - Managed Instance Group with scanner VMs
  - Service accounts for scanner operations
  - Secret Manager secret for API key

- **Scanned Projects:**
  - Impersonated service account for cross-project scanning

## Building

From the `gcp/` directory:

```bash
./agentless/build.sh
```

## Testing

```bash
cd agentless
pip install -r ../dev_requirements.txt
pytest
```
