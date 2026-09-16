# MWAA Setup Diagnostics

Surveys Amazon MWAA environments for a Data Observability / OpenLineage onboarding plan,
and applies it. `scan` reads `requirements.txt`/`constraints.txt`/the startup script and
`airflow_configuration_options`, computes a per-environment plan and a set of `issues` --
package pins, `--constraint` path and referenced-wheel existence, the execution role's S3
access, and whether OpenLineage is configured two different ways at once (the startup
script and `airflow_configuration_options`, which Datadog's own
[MWAA/OpenLineage upgrade guide](https://docs.datadoghq.com/data_observability/jobs_monitoring/airflow_mwaa_upgrade.md)
doesn't cover) -- and persists both as a session. `apply` loads that session and applies
one named environment's plan.

`scan` makes no changes to the environment: every call it makes is a read
(`mwaa:GetEnvironment`, `s3:GetObject`/`HeadObject`, `iam:SimulatePrincipalPolicy`), and
that's enforced mechanically, not just by review -- see `MwaaClient`'s `read_only` guard
in `shared/src/airflow_shared/mwaa_client.py`.

The produced executable is intended to run in [AWS CloudShell](https://aws.amazon.com/cloudshell/),
which has `boto3` preinstalled. It can also be run locally against any MWAA environment
you have read access to.

---

# Usage

```bash
# Survey every environment in a region, persist the session, point back to the UI
python mwaa.pyz scan --session-id <uuid> --region us-east-1 --dd-api-key <key>

# Same, but walk the whole select/review/apply flow at the terminal instead
python mwaa.pyz scan --session-id <uuid> --region us-east-1 --dd-api-key <key> --interactive

# Preview one environment's plan from a session a prior `scan` persisted
python mwaa.pyz apply --session-id <uuid> --name my-mwaa-environment --region us-east-1 --dd-api-key <key>
# ...then add --yes once the diff looks right, to actually apply it
```

`--region` falls back to `AWS_REGION`/`AWS_DEFAULT_REGION` if omitted, and `--dd-api-key`
falls back to `DD_API_KEY`. `--session-id` must be a UUID -- the eventual UI generates one
and embeds it in the command it hands you.

A session's proposed startup.sh never carries a real Datadog API key -- only a
placeholder (see `startup_script.py`). Both `scan` and `apply` require `--dd-api-key`,
but only `apply` (or `scan --interactive`, right before it applies) ever substitutes the
real value in, immediately before a file is previewed or written. Nothing persisted or
displayed upstream of that point -- including anything that would eventually be sent to
a backend -- ever contains the real key.

AWS credentials are picked up the normal boto3 way (CloudShell's assumed role, an
environment profile, `~/.aws/credentials`, etc.) -- this tool does not manage credentials
itself.

If `scan` recorded any `issues` for the environment you `apply` (a conflicting OpenLineage
config, a missing constraints/wheel file, an execution role that can't read what the plan
would write), they're printed before the diff. They don't block applying.

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
SESSION_OVERRIDE_PATH=./my-session.json python mwaa.pyz apply --session-id <uuid> --name my-mwaa-environment --region us-east-1 --dd-api-key <key> --yes
```

Not part of the documented CLI surface for customers -- it's a testing escape hatch.

### Build

From the `airflow/` folder:

```bash
bash mwaa/build.sh
```

Produces `mwaa/dist/mwaa.pyz`. Rebuild and commit `dist/` together with any change under
`mwaa/src/`, `mwaa/build.sh`, or `shared/src/`.
