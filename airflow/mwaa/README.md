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
# Read-only diagnostics against one environment
python mwaa.pyz probe --name my-mwaa-environment --region us-east-1

# Survey every environment in a region, persist the session, point back to the UI
python mwaa.pyz scan --session-id <uuid> --region us-east-1 --dd-api-key <key>

# Same, but walk the whole select/review/apply flow at the terminal instead
python mwaa.pyz scan --session-id <uuid> --region us-east-1 --dd-api-key <key> --interactive

# Preview one environment's plan from a session a prior `scan` persisted
python mwaa.pyz apply --session-id <uuid> --name my-mwaa-environment --region us-east-1
# ...then add --yes once the diff looks right, to actually apply it
```

`--name`/`--region` fall back to `MWAA_ENVIRONMENT_NAME`/`AWS_REGION` (or
`AWS_DEFAULT_REGION`) if omitted, and `--dd-api-key` falls back to `DD_API_KEY`.
`--session-id` must be a UUID -- the eventual UI generates one and embeds it in
the command it hands you. `--dd-api-key` is interpolated directly into the
proposed startup.sh, since the script needs the real value to actually work.

AWS credentials are picked up the normal boto3 way (CloudShell's assumed role, an
environment profile, `~/.aws/credentials`, etc.) -- this tool does not manage credentials
itself.

`probe`'s exit code is non-zero if any check fails.

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

### Testing `apply` against an arbitrary session

`apply --session-id <id>` normally loads the Session a prior `scan --session-id <id>`
persisted (see `session_store.py`) and pulls out the plan for `--name` from it. For
local/dev testing, setting `SESSION_OVERRIDE_PATH` to a JSON file skips that lookup and
uses the Session in the file instead -- useful for driving a real environment into a
specific state without running `scan` first. `--session-id`/`--name`/`--region` are all
still required flags either way; the override only swaps out where the Session's *content*
comes from. The expected shape is exactly what `scan` persists
(`dataclasses.asdict(session)`): copy one out of `/tmp/mwaa-session-<id>.json`, edit it,
feed it back in.

```bash
SESSION_OVERRIDE_PATH=./my-session.json python mwaa.pyz apply --session-id <uuid> --name my-mwaa-environment --region us-east-1 --yes
```

Not part of the documented CLI surface for customers -- it's a testing escape hatch.

### Build

From the `airflow/` folder:

```bash
bash mwaa/build.sh
```

Produces `mwaa/dist/mwaa.pyz`. Rebuild and commit `dist/` together with any change under
`mwaa/src/`, `mwaa/build.sh`, or `shared/src/`.
