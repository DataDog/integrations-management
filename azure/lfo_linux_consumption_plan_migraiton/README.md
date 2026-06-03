# LFO Linux Consumption → Container App Jobs migration

One-shot Python script run from Azure Cloud Shell that migrates an existing LFO
control plane from the Linux Consumption Function Apps (`resources-task-*`,
`scaling-task-*`, `diagnostic-settings-task-*`) to Container App Jobs running in
the deployer's existing Container App environment.

See `instructions.txt` for the source-of-truth requirements and `PLAN.md` for
the implementation plan.

## Development

Build (from the `azure/` directory):

```bash
bash lfo_linux_consumption_plan_migraiton/build.sh
```

Test (from the `azure/` directory):

```bash
python -m pytest lfo_linux_consumption_plan_migraiton/tests
```

Run locally (from the `azure/lfo_linux_consumption_plan_migraiton/` directory):

```bash
PYTHONPATH=../shared/src:src python -m azure_lfo_consumption_plan_migration [args]
```

## Usage

```bash
./azure_lfo_consumption_plan_migration.pyz \
  [--control-plane-subscription SUB_ID] \
  [--control-plane-id ID] \
  [--dry-run] \
  [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

With no filters, the script discovers every LFO control plane the current
user's Azure CLI session can see via Azure Resource Graph and migrates each.
Use the filters to scope to a single control plane (staged rollout / debugging).
