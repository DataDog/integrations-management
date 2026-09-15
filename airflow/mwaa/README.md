# MWAA Setup Diagnostics

Read-only diagnostics for an Amazon MWAA environment's Data Observability / OpenLineage
onboarding setup. Checks `requirements.txt`/`constraints.txt` resolution, package pins,
the execution role's S3 access, install logs, and network egress -- the things Datadog's
[MWAA/OpenLineage upgrade guide](https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow_mwaa_upgrade.md)
calls out as common onboarding failure modes -- plus one thing that guide doesn't cover:
whether OpenLineage settings from the startup script and from `airflow_configuration_options`
agree, when both are set.

It makes no changes to the environment. Every check is a read: `mwaa:GetEnvironment`,
`s3:GetObject`/`HeadObject`, `logs:FilterLogEvents`, `iam:SimulatePrincipalPolicy`,
`ec2:DescribeSubnets`/`DescribeRouteTables`.

The produced executable is intended to run in [AWS CloudShell](https://aws.amazon.com/cloudshell/),
which has `boto3` preinstalled. It can also be run locally against any MWAA environment
you have read access to.

---

# Usage

```bash
python mwaa.pyz --name my-mwaa-environment --region us-east-1
```

Both flags fall back to environment variables if omitted: `MWAA_ENVIRONMENT_NAME` and
`AWS_REGION` (or `AWS_DEFAULT_REGION`).

AWS credentials are picked up the normal boto3 way (CloudShell's assumed role, an
environment profile, `~/.aws/credentials`, etc.) -- this tool does not manage credentials
itself.

Exit code is non-zero if any check fails.

---

# Development

### Dev Setup

```bash
cd airflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r dev_requirements.txt -r requirements.txt
```

### Testing

Run from the `airflow/` folder so `shared/src` resolves:

```bash
cd airflow
python -m pytest mwaa/tests
```

### Build

From the `airflow/` folder:

```bash
bash mwaa/build.sh
```

Produces `mwaa/dist/mwaa.pyz`. Rebuild and commit `dist/` together with any change under
`mwaa/src/`, `mwaa/build.sh`, or `shared/src/`.
