# LFO Linux Consumption Plan → Container App Jobs migration — plan

Customer-run Python script (Azure Cloud Shell) that migrates an existing LFO
control plane from Function Apps (Linux Consumption) to Container App Jobs.

## Package shape

New zipapp following the `logging_install` / `agentless` convention:

```
azure/lfo_linux_consumption_plan_migraiton/
├── build.sh                         # zip src/ + shared/src into dist/azure_lfo_consumption_plan_migration.pyz
├── pytest.ini
├── README.md
├── dist/
├── src/
│   └── azure_lfo_consumption_plan_migration/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py                  # arg parsing, top-level orchestration
│       ├── constants.py             # placeholder image URLs, role IDs, job sizing/cron defaults
│       ├── discovery.py             # ARG queries → list of control planes to migrate
│       ├── migration.py             # per-control-plane state machine (phases 1–5)
│       ├── steps.py                 # Step abstraction (do/undo) + Runner with rollback stack
│       └── phases/
│           ├── setup.py             # Phase 1 helpers (locate deployer job + env, read env vars)
│           ├── create_jobs.py       # Phase 2 (3 paused Container App Jobs)
│           ├── roles.py             # Phase 3 (role assignments)
│           ├── enable.py            # Phase 4 (pause / trigger / unpause / image-bump)
│           └── cleanup.py           # Phase 5 (best-effort delete + manual-action log)
└── tests/
```

Reuses `az_shared` (`execute`, `AzCmd`, `log`, error types) and the existing
`RESOURCES_TASK_PREFIX` discovery pattern from
`azure/logging_install/src/azure_logging_install/existing_lfo.py`.

## CLI

```
azure_lfo_consumption_plan_migration.pyz \
  [--control-plane-subscription SUB_ID]   # optional filter
  [--control-plane-id ID]                 # optional filter (12-char suffix)
  [--dry-run]                             # log planned az commands without executing
  [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

No filters → migrate every LFO control plane the user can see. Filters narrow
the ARG result set.

## Step / rollback abstraction (`steps.py`)

```python
@dataclass
class Step:
    name: str
    do: Callable[[], None]
    undo: Callable[[], None] | None        # None = no rollback (Phase 5)

class Runner:
    def run(self, steps): ...               # push completed step onto stack;
                                            # on exception run undo for top, then unwind
```

- Idempotency lives inside each `do`: every create-call does a "show" first and
  skips on existence; every delete swallows `ResourceNotFoundError`.
- Phase 5 steps are added with `undo=None`; errors are caught and surfaced in a
  final "Manual cleanup required" report instead of rolling back.

## Per-control-plane flow

### Phase 1 — Setup (idempotent, no real side effects → no rollback)

1. ARG query for `microsoft.web/sites` where `name startswith 'resources-task-'`,
   optionally filtered by `--control-plane-subscription` / `--control-plane-id`.
   Build `LfoControlPlane` records (mirrors `find_existing_lfo_control_planes`).
2. For each control plane, locate by name suffix `<id>`:
   - Deployer Container App Job: `deployer-task-<id>`
   - Container App Environment: `dd-log-forwarder-env-<id>-<region>`
   - The 3 existing function apps: `resources-task-<id>`, `scaling-task-<id>`,
     `diagnostic-settings-task-<id>`
3. Pull env vars off each function app
   (`functionapp config appsettings list`) — source of truth for
   `MONITORED_SUBSCRIPTIONS`, `RESOURCE_TAG_FILTERS`, `PII_SCRUBBER_RULES`, etc.

### Phase 2 — Create 3 paused Container App Jobs

For each task (`resources-task`, `scaling-task`, `diagnostic-settings-task`):

- **do**: if a Container App Job with the same name already exists → skip.
  Otherwise `az containerapp job create` with:
  - `--name <task>-job-<id>` (`-job-` suffix avoids the resource-type-shared
    namespace surprise with the still-living function app, and makes Phase 5
    ordering unambiguous)
  - `--environment` = the existing env
  - `--trigger-type Manual` (the "paused" form — never fires on its own)
  - `--mi-system-assigned`
  - `--image <PLACEHOLDER from constants.py>`
  - `--env-vars` copied verbatim from the corresponding function app's
    appsettings, filtered to drop function-runtime-only keys
    (`AzureWebJobsStorage`, `FUNCTIONS_EXTENSION_VERSION`,
    `FUNCTIONS_WORKER_RUNTIME`, `WEBSITE_CONTENTAZUREFILECONNECTIONSTRING`,
    `AzureWebJobsFeatureFlags`)
  - Storage connection string passed as `--secrets` + `secretref:` env, matching
    the deployer-job pattern in `resource_setup.py:create_container_app_job`
  - `--replica-timeout`, `--cpu`, `--memory`, `--parallelism`,
    `--replica-completion-count` → defaults in `constants.py`, easy to tweak
- **undo**: `az containerapp job delete --yes` (swallow not-found)

### Phase 3 — Role assignments

Read `MONITORED_SUBSCRIPTIONS` from the resources-task function app env. For
each monitored sub, get each new job's managed-identity principalId via
`containerapp job show --query identity.principalId` (mirrors
`get_container_app_job_principal_id` in `role_setup.py`).

| Job                        | Scope                              | Role                                                         |
|----------------------------|------------------------------------|--------------------------------------------------------------|
| diagnostic-settings-job    | forwarder RG (per monitored sub)   | Reader and Data Access (`STORAGE_READER_AND_DATA_ACCESS_ID`) |
| diagnostic-settings-job    | subscription                       | Monitoring Contributor (`MONITORING_CONTRIBUTOR_ID`)         |
| scaling-job                | forwarder RG (per monitored sub)   | Contributor (`SCALING_CONTRIBUTOR_ID`)                       |
| resources-job              | subscription                       | Monitoring Reader (`MONITORING_READER_ID`)                   |
| deployer (existing job)    | control plane RG                   | **Container Apps Jobs Contributor** (built-in, replaces Website Contributor) |

- The Container Apps Jobs Contributor role is a built-in Azure role. Its GUID
  goes in `constants.py` as `CONTAINER_APPS_JOBS_CONTRIBUTOR_ID`. No custom role
  definition required.
- **do** for each: skip if assignment exists (reuse `role_exists`).
- **undo**: `az role assignment delete` for each created assignment.

### Phase 4 — Enablement

Sequential steps, each with a rollback:

1. **Stop deployer job** — `az containerapp job stop --name deployer-task-<id>`.
   *Undo:* re-trigger via `az containerapp job start` (or rely on the schedule
   resuming on its own — record honestly in the rollback log).
2. **Stop the 3 function apps** — `az functionapp stop`. *Undo:*
   `az functionapp start`.
3. **Manually trigger each new job once and wait** —
   `az containerapp job start` then poll `containerapp job execution show` for
   status. If any execution lands in `Failed` / `Degraded`, raise → rollback
   unwinds (restart functions, restart deployer). This is the "abort the update
   for stuck customers" gate from the instructions.
4. **Convert the 3 new jobs from Manual to Schedule (unpause)** —
   `az containerapp job update --trigger-type Schedule --cron-expression
   '<task-specific cron>'` (crons in `constants.py`). *Undo:* set trigger back
   to Manual.
5. **Bump deployer image** — `containerapp job update --image
   <NEW_DEPLOYER_IMAGE placeholder>`. *Undo:* set image back to the prior value
   (capture it before update).
6. **Resume deployer schedule** — re-enable the schedule (or start it once to
   confirm). *Undo:* stop deployer.

### Phase 5 — Cleanup (no rollback; failures → "manual action required")

- Delete the 3 function apps: `az functionapp delete`.
- Delete the consumption-plan app service plan(s) the function apps were on
  (discover the plan referenced by each function app rather than guessing the
  name).
- Delete the `control-plane-cache` file share on the storage account (keep the
  storage account + blob container — still used by jobs for the cache
  connection string).
- Remove the deployer's old Website Contributor role assignment on the
  control-plane RG.

Every failure here is caught, accumulated in a `manual_cleanup_actions` list,
and printed at the end so the customer can run them by hand.

## Placeholders in `constants.py`

Editable without code changes:

- `RESOURCES_TASK_IMAGE`, `SCALING_TASK_IMAGE`,
  `DIAGNOSTIC_SETTINGS_TASK_IMAGE`, `NEW_DEPLOYER_IMAGE` — placeholder strings.
- `*_TASK_CRON` — the schedule each new job switches to when unpaused.
- Job sizing defaults (`cpu`, `memory`, `replica-timeout`,
  `replica-retry-limit`).
- `CONTAINER_APPS_JOBS_CONTRIBUTOR_ID` — built-in role GUID.

## Open items

1. **Job naming**: proposed `<task>-job-<id>` so the new jobs and old function
   apps don't share names. Azure allows the same name across different resource
   types, but reusing `<task>-<id>` complicates ARG discovery for future scripts
   and reverses Phase 5 ordering (functions must be deleted before jobs are
   created).
2. **App service plan deletion**: the script discovers the plan(s) referenced
   by the function apps before deleting them rather than guessing the name.
3. **Deployer image rollback**: rollback after Phase 4 step 5 restores the
   image tag captured pre-update; if the new image already wrote incompatible
   state to storage on its first run, that state isn't undone. Real-world
   rollback may require a manual data fix — documented in the rollback log
   message rather than pretended to be clean.
