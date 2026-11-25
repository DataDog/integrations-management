# Set up Datadog Data Observability on Amazon MWAA

You are helping me connect one or more Amazon MWAA (Managed Workflows for Apache Airflow)
environments to Datadog Data Observability, so that Airflow sends OpenLineage events to
Datadog. Follow this document exactly. It encodes the same rules as Datadog's own setup CLI
(`mwaa.pyz`), so the result is the same whichever way we do it.

My Datadog site is `{{DD_SITE}}`. Events go to `https://data-obs-intake.{{DD_SITE}}`.

## 0. Ground rules (apply throughout)

1. **Never change anything without my explicit "yes" in this conversation.** That covers
   any S3 upload, any `aws mwaa update-environment`, and any `apply`. Before asking, show the
   exact file diffs and the exact commands.
2. **Keep everything else as it is.** Never remove or reorder my other packages, pins, or
   startup-script lines. Only add or correct the specific lines these rules name.
3. **One environment at a time.** Finish (or stop) one before starting the next.
4. **The Datadog API key is a secret.**
   - Ask me for it, or read it from the `DD_API_KEY` environment variable if I say it's set.
     It's never in this document.
   - Never print it in full. Anywhere you show it (diffs, commands, logs, summaries, a
     key already in my files), mask it as `****` plus its last 4 characters.
   - Pass it to commands through the `DD_API_KEY` environment variable, not on a command line.
   - The files you upload must contain the real key; only what you display is masked.
5. **When a rule says STOP, stop.** Explain the problem in plain language, say what I need to
   do, and wait. Don't improvise a workaround.
6. If anything here conflicts with what you find, tell me. Don't guess.

## 1. Collect context first

Ask me, in one message:

1. The AWS region, and the MWAA environment name(s). If I don't know them,
   `aws mwaa list-environments --region <region>` lists them.
2. How we'll work:
   - **(A) the setup CLI.** You can run Python and the AWS CLI with my credentials in your
     shell. This is the preferred mode because it's lossless.
   - **(B) AWS CLI by hand.** You can run the AWS CLI, but not the setup CLI.
   - **(C) guided manual.** You can't reach AWS; I'll paste files and console values, and
     you'll tell me exactly what to upload and click.
3. The Datadog API key (or confirmation that `DD_API_KEY` is set). Remind me it should be a
   key from the `{{DD_SITE}}` organization I'm onboarding.
4. Optionally, a session ID if the Datadog page gave me one (a UUID). It lets the page follow
   along.

## 2. Mode A: drive the setup CLI (preferred)

The CLI applies every rule below itself, verifies the result statically, and masks keys in
its output.

1. Check prerequisites: `python3 --version` (3.9+), `python3 -c "import boto3"`, and
   `aws sts get-caller-identity`. If boto3 is missing, use mode B, or AWS CloudShell, which
   has boto3.
2. Download the CLI: `curl -fsSL -o mwaa.pyz "{{MWAA_PYZ_URL}}"`.
3. Scan (read-only; it changes nothing):
   - **With a session ID from the Datadog page:**
     `DD_API_KEY=<key> python3 mwaa.pyz scan --session-id <id> --region <region> --dd-site {{DD_SITE}}`
   - **Without one:** generate a UUID (`python3 -c "import uuid; print(uuid.uuid4())"`) and run
     `DD_API_KEY=<key> python3 mwaa.pyz scan --session-id <uuid> --region <region> --dd-site {{DD_SITE}} --offline`.
     The plan is then saved to `<tmp>/mwaa-session-<uuid>.json`.
   - Always pass `--dd-site {{DD_SITE}}`. With `--offline` and no site, the CLI assumes
     datadoghq.com.
4. Explain the plan for my environment in plain language, from the session JSON or the
   `apply` preview: each file change, each issue (FAIL blocks, WARN doesn't), and what the
   update will restart. Use the rules in section 5 to explain *why*.
5. Preview: `DD_API_KEY=<key> python3 mwaa.pyz apply --session-id <id> --name <env> --region <region> --dd-site {{DD_SITE}}`
   (add `--offline` if the scan used it).
   - It prints the masked diffs, then asks for confirmation if it has a terminal.
   - Without a terminal and without `--yes`, it exits non-zero with "Not applied: confirm
     interactively or pass --yes". That's expected: it means nothing was changed.
6. Show me the preview and ask: "Apply these changes and restart <env>?" Only after I answer
   yes, re-run the same command with `--yes`.
   - If apply says a file changed since the scan, re-scan.
   - If it reports a FAIL issue, follow that issue's instructions and re-scan.
7. Continue with section 6 (wait and verify).

## 3. Mode B: apply the rules with the AWS CLI

Gather everything with read-only calls, compute the changes with section 5, show them, and
write only after my yes.

**Read (no changes):**

```sh
aws mwaa get-environment --name <env> --region <region>
# note: AirflowVersion, SourceBucketArn (bucket = after the last ':'), DagS3Path,
# RequirementsS3Path + RequirementsS3ObjectVersion, StartupScriptS3Path +
# StartupScriptS3ObjectVersion, AirflowConfigurationOptions, ExecutionRoleArn,
# WebserverUrl, LoggingConfiguration

aws s3api list-object-versions --bucket <bucket> --prefix <key> --max-items 5   # latest version of each file below
aws s3api get-object --bucket <bucket> --key <key> [--version-id <v>] <local-file>
aws s3api head-object --bucket <bucket> --key <key>   # existence; a 403 instead of 404 means no s3:ListBucket -> STOP (rule 5.3)
aws s3 ls s3://<bucket>/<DagS3Path>/                   # wheels, constraints files, startup scripts in the DAGs folder
```

Files to read:
- requirements.txt and the startup script (configured path, latest version);
- the constraints file requirements.txt references, if it's under the DAGs folder;
- the default-named files the placement rule (5.3) checks for.

Record each one's **latest VersionId**. Right before writing, re-read them, and STOP if any
changed (someone else uploaded meanwhile).

**Write (only after my yes), in this order:**
1. Download any 2.7.2 wheels (rule 5.6). Confirm each starts with the zip bytes `PK`.
   Upload them with `aws s3 cp <file> s3://<bucket>/<DagS3Path>/<wheel filename>`.
2. Upload the constraints file, then requirements.txt, then the startup script, each with
   `aws s3api put-object --bucket <bucket> --key <key> --body <file>`. Record the returned
   `VersionId`.
3. Only if requirements.txt or the startup script was written, run (including only the
   pairs for the files written):

   ```sh
   aws mwaa update-environment --name <env> --region <region> \
     --requirements-s3-path <key> --requirements-s3-object-version <VersionId> \
     --startup-script-s3-path <key> --startup-script-s3-object-version <VersionId>
   ```

   A constraints-file or wheel upload alone needs no update; MWAA reads them on its next
   install.

Validate the API key per rule 5.10 (one `curl`; mask the key in anything you print).

## 4. Mode C: guided manual

Ask me to paste:
- from the MWAA console, Environment details: Airflow version, S3 bucket, DAG code path,
  requirements file path and version, startup script path and version, Airflow
  configuration options;
- the content of requirements.txt, the startup script, and the constraints file
  requirements.txt points at (if it's a file in the DAGs folder);
- a listing of the DAGs folder and of the folder containing requirements.txt (S3 console,
  object names only);
- for requirements.txt and the startup script, whether "Show versions" lists a newer
  version than the one the environment uses.

Then compute the exact new files with section 5. Give me each full file to download or
copy, plus the diff against what I have. Walk me through:
1. Uploading each file to its exact S3 key (wheels first, then constraints, requirements,
   startup script).
2. Edit environment: select the new object version for requirements.txt and the startup
   script; set the startup script path if none was configured.
3. Save. This starts the update (20-30 minutes, see section 6).

## 5. The rules

`<DAGS>` is the environment's `DagS3Path` in S3. Inside the environment, the same folder is
mounted at `/usr/local/airflow/dags/`.

### 5.1 Is the Airflow version flagged?

Datadog's MWAA upgrade guide flags three versions whose Airflow constraints pin a broken
OpenLineage provider. Their target pins, the transitive constraint bumps they need, and
whether MWAA itself forces the upstream constraints file when requirements.txt has no
`--constraint` line (observed on real environments: "Forcing local constraints" in the
`requirements_install` log):

| Airflow | Python | Broken default provider | MWAA forces upstream constraints without `--constraint`? |
|---|---|---|---|
| 2.7.2 | 3.11 | `apache-airflow-providers-openlineage==1.1.0` | 2.7.2: mwaa_forces_upstream_constraints = true |
| 2.8.1 | 3.11 | `apache-airflow-providers-openlineage==1.4.0` | 2.8.1: mwaa_forces_upstream_constraints = false |
| 2.9.2 | 3.11 | `apache-airflow-providers-openlineage==1.8.0` | 2.9.2: mwaa_forces_upstream_constraints = true |

Target pins:

- **2.7.2:**
  - `apache-airflow-providers-openlineage==1.14.0` (Datadog-patched wheel, rule 5.6)
  - `apache-airflow-providers-common-compat==1.2.2` (Datadog-patched wheel, rule 5.6)
  - `openlineage-integration-common==1.24.2`
  - `openlineage-python==1.24.2`
  - `openlineage-sql==1.24.2`
  - `apache-airflow-providers-common-sql` stays at the constraints' 1.7.2.
  - No constraint bumps.
- **2.8.1:**
  - `apache-airflow-providers-openlineage==1.14.0`
  - `apache-airflow-providers-common-sql==1.20.0`
  - `apache-airflow-providers-common-compat==1.2.1`
  - `openlineage-integration-common==1.24.2`
  - `openlineage-python==1.24.2`
  - `openlineage-sql==1.24.2`
  - Constraint bump: `sqlparse==0.5.1` (apache-airflow-providers-common-sql 1.20.0 needs sqlparse>=0.5.1).
- **2.9.2:**
  - `apache-airflow-providers-openlineage==2.2.0`
  - `apache-airflow-providers-common-sql==1.21.0`
  - `apache-airflow-providers-common-compat==1.4.0`
  - `openlineage-integration-common==1.31.0`
  - `openlineage-python==1.31.0`
  - `openlineage-sql==1.31.0`
  - Constraint bump: `sqlparse==0.5.1` (apache-airflow-providers-common-sql 1.21.0 needs sqlparse>=0.5.1).

Every other Airflow version is **unflagged**: MWAA's own constraints already resolve a
healthy provider. Skip to 5.8 for requirements.txt; there are no constraints-file changes.

Package names compare case-insensitively, with `-`, `_` and `.` treated as the same. So the
upstream files' `openlineage_sql==…` line **is** the `openlineage-sql` pin. Rewrite it in
place, under the canonical name, and remove any other line pinning the same project. Pip
enforces every pin, and a leftover `openlineage_sql==1.7.0` next to `openlineage-sql==1.24.2`
is a ResolutionImpossible.

### 5.2 Stop conditions (check before planning)

- **More than one `--constraint` line in requirements.txt** (flagged versions): STOP. Pip
  enforces all of them, so ask me to consolidate them into one.
- **The `--constraint` reference can't be read**: a `/usr/local/airflow/dags/...` file that
  doesn't exist in S3, a plain `http://` URL, a path neither under `/usr/local/airflow/dags/`
  nor `https://`, an `https://` URL that won't download, or an Apache-hosted URL
  (`raw.githubusercontent.com/apache/airflow/constraints-<v>/constraints-<py>.txt`) for a
  different Airflow or Python version than the environment's (the table above). STOP: its
  pins may still be in force, so I have to fix the reference.
- **A `.whl` that requirements.txt references under `/usr/local/airflow/dags/` doesn't exist in
  S3**: STOP (pip would fail 20-30 minutes into the update). A wheel outside the DAGs folder
  can't be verified: warn.
- **The execution role** (`ExecutionRoleArn`) lacks `s3:GetObject` or `s3:ListBucket` on the
  bucket: STOP. Check with
  `aws iam simulate-principal-policy --policy-source-arn <role> --action-names s3:GetObject s3:ListBucket --resource-arns <bucket ARN> <bucket ARN>/*`.
  If you can't run that, warn that it's unverified.
- **OpenLineage disabled**: `AIRFLOW__OPENLINEAGE__DISABLED` or `OPENLINEAGE_DISABLED` is
  `true`/`1`/`t`. STOP; ask me to remove it.
- **A transport you can't fix**: see 5.9.
- **You can't tell whether a default-named file exists** (403 instead of 404): STOP; it needs
  `s3:ListBucket`.

### 5.3 Which file to write

- **requirements.txt**: the configured `RequirementsS3Path`. If none is configured: the
  default key `requirements.txt` beside the DAGs folder's parent (`<prefix>/dags` gives
  `<prefix>/requirements.txt`; `dags` gives `requirements.txt`). If that key already exists,
  it isn't this environment's (it may be another environment's). Leave it alone and write
  `requirements-datadog.txt` in the same folder instead, then point the environment at it.
- **startup script**: the configured `StartupScriptS3Path`. If none is configured:
  `<DAGS>/startup.sh`, or `<DAGS>/startup-datadog.sh` if `startup.sh` already exists.
- **constraints file** (flagged versions):
  - requirements.txt's `--constraint "/usr/local/airflow/dags/<name>"`: patch that file in
    place, whatever it's named;
  - otherwise `<DAGS>/constraints.txt`, or `<DAGS>/constraints-datadog.txt` if
    `constraints.txt` already exists but requirements.txt doesn't reference it.
- Name the real S3 keys when you show me files.

### 5.4 Newer uploads the environment doesn't run yet

If requirements.txt or the startup script has a newer S3 version than the configured
`...S3ObjectVersion`, build on the **latest** version. Then:
- if the plan writes that file, the new version you upload includes my newer edits, and the
  update deploys both. Tell me so;
- if the plan doesn't touch that file, warn that this update won't deploy my newer upload.
  The environment keeps running the configured version, and the environment doesn't yet run
  what you checked.

### 5.5 The constraints file (flagged versions)

The base the OpenLineage pins are patched into:

1. requirements.txt references a local file under `/usr/local/airflow/dags/`: **that file**,
   patched in place.
2. requirements.txt references an `https://` URL: **that file's content** (downloaded),
   written to the file from 5.3. The `--constraint` line is replaced (not duplicated) to
   point at it.
3. No `--constraint` line: mirror what MWAA already applies (table in 5.1):
   - **forcing versions (2.7.2, 2.9.2):** the full upstream file
     `https://raw.githubusercontent.com/apache/airflow/constraints-<airflow>/constraints-<python>.txt`,
     i.e. `https://raw.githubusercontent.com/apache/airflow/constraints-2.7.2/constraints-3.11.txt`
     or `https://raw.githubusercontent.com/apache/airflow/constraints-2.9.2/constraints-3.11.txt`.
     A minimal file here would switch MWAA's forcing off and let my unpinned packages jump
     major versions (pandas 2 → 3, numpy 1 → 2). If it can't be downloaded, STOP; never fall
     back to a minimal file.
   - **2.8.1** (MWAA forces nothing): a minimal file with just the target pins. The full
     upstream file would newly enforce old pins and break newer ones I pin myself (boto3,
     say).

Then:
- set every target pin from 5.1. Rewrite an existing pin line in place (any spelling), drop
  duplicate pins of the same project, and append missing ones. On 2.7.2 that includes the two
  wheel packages, at the wheel versions;
- apply the version's constraint bump only if the base pins that package **below** the
  minimum (PEP 440: `0.5.1rc1` and `0.5.1.dev1` are below `0.5.1`; `0.5.1.post1` isn't). Never
  lower a pin, and never add one that isn't there.

Minimal file (2.8.1), exactly:

```text
# Pins only the OpenLineage packages Datadog Data Observability needs; MWAA applies no constraints of its own on this Airflow version, so every other package resolves as it did before.
apache-airflow-providers-openlineage==1.14.0
apache-airflow-providers-common-sql==1.20.0
apache-airflow-providers-common-compat==1.2.1
openlineage-integration-common==1.24.2
openlineage-python==1.24.2
openlineage-sql==1.24.2
```

Under forced constraints (case 3 on 2.7.2/2.9.2), warn about any direct `pkg==x` pin in
requirements.txt (other than the OpenLineage targets) that differs from the patched file,
for example: "boto3==1.35.0 conflicts with the Airflow constraints MWAA applies; pip will fail
to install requirements.txt until it matches." That was already failing before onboarding.

### 5.6 Airflow 2.7.2: Datadog-patched wheels

The upstream 1.14.0 provider isn't compatible with 2.7.2, so two packages come from wheels:
- `https://docs.datadoghq.com/resources/whl/apache_airflow_providers_openlineage-1.14.0-py3-none-any.whl`
- `https://docs.datadoghq.com/resources/whl/apache_airflow_providers_common_compat-1.2.2-py3-none-any.whl`

For each one:
1. Download it, check that it's a zip (it starts with `PK`), and upload it to `<DAGS>/<filename>`.
2. In requirements.txt, the line `/usr/local/airflow/dags/<filename>` **replaces** whatever line
   installs that package (a pin, a bare name, another wheel). If nothing does, append it.
3. If requirements.txt already references that wheel (any spelling of the name) and the
   object exists, there's nothing to do. If the reference exists but the object is missing,
   upload it.

The constraints file still pins both packages, at the wheel versions (1.14.0 and 1.2.2).

### 5.7 requirements.txt (flagged versions)

- Every target pin from 5.1 that isn't a wheel package: set `pkg==version`. Rewrite an
  existing `==` pin line in place (any spelling), otherwise append it.
- The `--constraint` line: if requirements.txt has none, **prepend**
  `--constraint "/usr/local/airflow/dags/<constraints filename>"`. If it has a URL one,
  replace it with that line. If it already points at the local file being patched, leave it.
- Keep every other line exactly as it was.

### 5.8 requirements.txt (unflagged versions)

If no line installs `apache-airflow-providers-openlineage` (any spelling), append the bare
line `apache-airflow-providers-openlineage` (no version: MWAA's constraints pick it).
Otherwise, change nothing.

If the provider appears only in the startup script (installed there, for example with
`pip install`), warn: it can't be verified, and requirements.txt is the right place. In that
case the environment doesn't count as configured.

### 5.9 Where OpenLineage would send: resolve the effective configuration

The provider runs with `AirflowConfigurationOptions`' `openlineage.*` keys, which MWAA exports
as `AIRFLOW__OPENLINEAGE__<KEY>`, overlaid with what the startup script exports. Resolve in
this order (provider and openlineage-python precedence); the first that applies decides:

1. `[openlineage] disabled` / `OPENLINEAGE_DISABLED` true → STOP (5.2).
2. `AIRFLOW__OPENLINEAGE__CONFIG_CONN_ID` set, with provider ≥ 2.18.0 (or the provider version is
   unknown) → can't be verified statically: warn, propose no transport change.
3. `AIRFLOW__OPENLINEAGE__CONFIG_PATH` non-empty → a config file: warn, propose no transport
   change. (The 2.7/2.8 workaround sets it to `""`, which doesn't count.)
4. `AIRFLOW__OPENLINEAGE__TRANSPORT` (JSON) → that's the transport.
   - An `OPENLINEAGE_CONFIG` file only fills keys the JSON leaves unset. If it could change the
     outcome, warn.
   - If it's an `http`/`async_http` transport whose `url` is **any** Datadog intake
     (`https://data-obs-intake.<site>` for any Datadog site), but the wrong site or without a
     usable API key: **correct it in place**. Set `url` to `https://data-obs-intake.{{DD_SITE}}`
     and `auth` to `{"type": "api_key", "apiKey": "<key>"}`, and keep every other field (headers,
     timeout, …).
   - That's only allowed when the startup script assigns it exactly once, as a standalone
     `export AIRFLOW__OPENLINEAGE__TRANSPORT='…'` line. Anything else (set in
     `AirflowConfigurationOptions`, assigned twice, sharing its line with another command):
     STOP and ask me to fix it.
   - Write it single-quoted: `export AIRFLOW__OPENLINEAGE__TRANSPORT='{"type": "http", "url": "https://data-obs-intake.{{DD_SITE}}", "auth": {"type": "api_key", "apiKey": "<key>"}}'`.
   - If it sends to a **non-Datadog** backend: STOP. That's my choice of where events go.
     Explain that it overrides `OPENLINEAGE_URL`, and ask whether to remove it (or point it at
     Datadog) myself.
5. Otherwise, the env-style `OPENLINEAGE__TRANSPORT__*` variables. With provider < 2.6.0 they are
   ignored unless `OPENLINEAGE_URL` is also set.
6. Otherwise `OPENLINEAGE_URL` (+ `OPENLINEAGE_API_KEY`) is an HTTP transport.
7. Otherwise events go to the console (nowhere).

Version gates: `async_http` needs openlineage-python ≥ 1.35.0, and the lowercase `apikey` auth
field needs ≥ 1.38.0 (older clients read `api_key`, else `apiKey`). A `composite` transport is
fine if any child sends to the intake with a key. The installed version is the requirements.txt
pin (or wheel version), else the constraints file's pin. If it's unknown and it matters, warn.

### 5.10 The startup script

Target exports, in this order:

```sh
export OPENLINEAGE_URL=https://data-obs-intake.{{DD_SITE}}
export OPENLINEAGE_API_KEY=<key>
export AIRFLOW__OPENLINEAGE__NAMESPACE="${AIRFLOW_ENV_NAME}"
# Airflow 2.7.2 and 2.8.1 only:
export AIRFLOW__OPENLINEAGE__CONFIG_PATH=""
export AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS=""
```

The per-variable rules, judged against the **effective** configuration (5.9), not the
script's literal text:

- **`OPENLINEAGE_URL`:** set it only if it isn't already `https://data-obs-intake.{{DD_SITE}}`
  **and** setting it would make the transport resolve to the intake. If a higher-precedence
  transport wins, or the outcome can't be told, don't touch it.
- **`OPENLINEAGE_API_KEY`:**
  - **missing or empty:** add it (with the same "would it take effect" condition).
  - **already set:** keep it, except for a **literal 32-hex key** typed into the assignment
    in effect (the last one). For that key:
    - next to an `OPENLINEAGE_URL` for **another** Datadog site, it's that site's key: replace
      it with my key;
    - otherwise check it with
      `curl -s -o /dev/null -w '%{http_code}' -X POST https://data-obs-intake.{{DD_SITE}}/api/v1/lineage -H "Content-Type: application/json" -H "Authorization: Bearer $EXISTING_KEY" -d '{}'`.
      2xx: keep it. 401/403: replace it and tell me it was rejected. Anything else or no
      network: keep it and warn that it's unverified.
  - **only edit it if** it's assigned once, on its own `export` line (keep a trailing
    comment). Otherwise tell me to replace it myself.
  - **never check or replace** a `$(…)`, a variable reference, or a secret lookup.
  - The same rules apply to a literal key inside a working Datadog
    `AIRFLOW__OPENLINEAGE__TRANSPORT`'s `auth`; fix it per 5.9.4.
- **`AIRFLOW__OPENLINEAGE__NAMESPACE`:** if it's set and non-empty, **never change it**. It's the
  `env` tag in Datadog and part of every job's identity, so renaming it forks job history. If
  it's missing or empty, set it to `"${AIRFLOW_ENV_NAME}"` (double-quoted so the shell expands
  it; MWAA sets `AIRFLOW_ENV_NAME` to the environment's name).
- **`AIRFLOW__OPENLINEAGE__CONFIG_PATH`** and **`AIRFLOW__OPENLINEAGE__DISABLED_FOR_OPERATORS`**
  (2.7.2/2.8.1 only): add them as `""` if they aren't defined at all. Defined, even empty,
  means leave them. A non-empty CONFIG_PATH is a config file (5.9.3), not something to blank.

How to edit:
- Replace an existing `export NAME=…` line for that variable in place, keeping a trailing
  `# comment`.
- Otherwise append at the end of the script.
- A new script starts with `#!/bin/sh`.
- Quoting: `NAMESPACE` and the empty workaround values are double-quoted, TRANSPORT is
  single-quoted, and the URL and key are bare.
- Never touch other lines.

### 5.11 Configuration set in two places

If an `openlineage.*` key in `AirflowConfigurationOptions` and a startup-script export set the
same variable to different values, warn. Which one wins on a worker isn't documented; a
diagnostic DAG (7.7) shows what's live.

### 5.12 Is it already configured?

It's configured when all of these hold:
- the provider is in requirements.txt;
- the transport (5.9) resolves to the intake with a key;
- a namespace is set;
- on 2.7.2/2.8.1, both workaround variables are defined;
- on flagged versions, the packages and constraints already match 5.5-5.7;
- no API key is known to be bad (5.10);
- no newer upload is pending (5.4).

If so, say there's nothing to change and go to section 6 to verify events.

### 5.13 The env tag

Tell me which `env:` tag my events will carry:
- the environment name when the namespace is (or will be) `${AIRFLOW_ENV_NAME}`;
- a literal namespace as is;
- unknown if it comes from `$(…)` or another variable;
- `default` if nothing sets one.

## 6. Wait and verify

1. **The update takes 20-30 minutes.** Check its progress with
   `aws mwaa get-environment --name <env> --query 'Environment.[Status,LastUpdate]'`.
   The status goes from `UPDATING` to `AVAILABLE`.
2. **MWAA reports SUCCESS even when pip fails.** Always check the install log:

   ```sh
   aws logs filter-log-events --log-group-name airflow-<env>-Worker \
     --log-stream-name-prefix requirements_install --filter-pattern '?ERROR ?ResolutionImpossible'
   ```

   Also check `airflow-<env>-Scheduler`. These log groups exist only if worker/scheduler
   logging is enabled (`LoggingConfiguration`); otherwise ask me to enable it, or to check in
   the CloudWatch console.
3. **Confirm the provider version:**
   - **Airflow 2.x:**

     ```sh
     TOKEN=$(aws mwaa create-cli-token --name <env> --query CliToken --output text)
     HOST=$(aws mwaa get-environment --name <env> --query Environment.WebserverUrl --output text)
     curl -s -X POST "https://$HOST/aws_mwaa/cli" -H "Authorization: Bearer $TOKEN" -H "Content-Type: text/plain" \
       -d "providers list" | python3 -c "import sys, json, base64; print(base64.b64decode(json.load(sys.stdin)['stdout']).decode())"
     ```

   - **Airflow 3:** the CLI endpoint isn't available; use
     `aws mwaa invoke-rest-api --name <env> --method GET --path /providers`.
   - Check that `apache-airflow-providers-openlineage` is at the target version.
4. Ask me to trigger any DAG. Then send me back to the Datadog page to watch for the first
   events, which are tagged `env:<namespace>` (5.13).

## 7. Triage playbook

1. **`ResolutionImpossible` in requirements_install** (nothing from requirements.txt got
   installed):
   - **My own pin conflicts with a constraint** (for example `boto3==1.34.11` vs a constraint
     of `1.33.13`): with no `--constraint` on 2.8.1, use the minimal file (5.5); on forcing
     versions, the pin was already failing, so align it.
   - **`common-sql` vs `sqlparse`** on 2.8.1/2.9.2 with a full constraints file: apply the
     `sqlparse==0.5.1` bump.
   - **Duplicate `openlineage_sql` and `openlineage-sql` pins**: keep one.
   - **To reproduce locally**: Python 3.11,
     `pip install --dry-run --ignore-installed -c <constraints> -r <requirements> apache-airflow==<v>`.
2. **Installed fine, but no events and no errors.** Usually a 401: the wrong site, or a stale
   key. The OpenLineage listener doesn't log failed deliveries at the default level.
   - Check the key with the curl in 5.10.
   - Check that `OPENLINEAGE_URL` is `https://data-obs-intake.{{DD_SITE}}`.
   - Check that the key belongs to the `{{DD_SITE}}` organization.
3. **A TRANSPORT override.** `AIRFLOW__OPENLINEAGE__TRANSPORT` (startup script or
   `openlineage.transport` in the configuration options) wins over `OPENLINEAGE_URL`. See 5.9.4.
4. **The change didn't take effect.** The environment still runs an older object version:
   `get-environment` shows the configured `...S3ObjectVersion`. Compare it with
   `list-object-versions` and update the environment to the new version.
5. **The startup script isn't attached.** It's uploaded, but `StartupScriptS3Path` is empty:
   set the path and its version in Edit environment.
6. **No events after a successful install.**
   - Did a DAG actually run after the update finished?
   - Look under the right `env:` tag (5.13).
   - Run the diagnostic DAG (item 7) and read its task log.
7. **Diagnostic DAG.** Upload it to `<DAGS>/`, trigger it, and read the task log:

   ```python
   import os
   from datetime import datetime
   from airflow import DAG
   from airflow.operators.python import PythonOperator

   def report():
       key = os.environ.get("OPENLINEAGE_API_KEY") or ""
       print("OPENLINEAGE_URL =", os.environ.get("OPENLINEAGE_URL"))
       print("OPENLINEAGE_API_KEY =", ("****" + key[-4:]) if key else "(unset)")
       for name in ("AIRFLOW__OPENLINEAGE__NAMESPACE", "AIRFLOW__OPENLINEAGE__TRANSPORT",
                    "AIRFLOW__OPENLINEAGE__CONFIG_PATH", "AIRFLOW__OPENLINEAGE__DISABLED"):
           value = os.environ.get(name)
           print(name, "=", "(set; may contain a key)" if name.endswith("TRANSPORT") and value else value)
       from importlib.metadata import version
       print("provider", version("apache-airflow-providers-openlineage"))

   with DAG("openlineage_diagnostics", start_date=datetime(2024, 1, 1), schedule=None, catchup=False):
       PythonOperator(task_id="report", python_callable=report)
   ```

   On Airflow 2.7.2/2.8.1, use `schedule_interval=None` if `schedule` isn't accepted.
8. **Airflow 3.** Use `aws mwaa invoke-rest-api` instead of the CLI-token endpoint for anything
   that would run an Airflow CLI command (6.3).

When we're done, summarize what changed (file keys and new object versions), what to watch,
and the `env:` tag. Mask any key in that summary.
