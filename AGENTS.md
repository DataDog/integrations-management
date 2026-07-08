# Agent instructions for `integrations-management`

These instructions apply to AI coding assistants (Claude Code, Cursor, etc.) working in this repo.

## Repo shape

This repo holds six self-contained Python packages, three per cloud:

| Path                              | What it builds                                       |
|-----------------------------------|------------------------------------------------------|
| `azure/agentless`                 | `azure_agentless_setup.pyz`                          |
| `azure/integration_quickstart`    | `azure_app_registration_quickstart.pyz`, `azure_log_forwarding_quickstart.pyz` |
| `azure/logging_install`           | `azure_logging_install.pyz` + bicep JSONs            |
| `gcp/agentless`                   | `gcp_agentless_setup.pyz`                            |
| `gcp/integration_quickstart`      | `gcp_integration_quickstart.pyz`                     |
| `gcp/log_forwarding_quickstart`   | `gcp_log_forwarding_quickstart.pyz`                  |

Each package has:

- `src/` — Python source.
- `tests/` — pytest tests; conventionally run from the cloud parent directory (`cd azure && python -m pytest <package>/tests`) so cross-package imports like `shared.tests.test_data` resolve.
- `build.sh` — packs `src/` (plus `shared/src/` and any other inputs) into a zipapp `.pyz` under `dist/`. For `azure/logging_install`, also compiles `bicep/*.bicep` to JSON.
- `dist/` — committed build output. The CI drift-check job rebuilds and diffs against this; if `dist/` is out of sync with `src/`, CI fails.

## Hard rule: build before pushing

If you change anything under a package's `src/`, `build.sh`, `bicep/`, or `<cloud>/shared/src/`, you MUST rebuild the affected `dist/` and commit it together with the source change. CI's `dist drift` job will reject the PR otherwise.

The reliable way is to rebuild the whole cloud in one command from the repo root — this covers the bundling graph (e.g. `shared/src/` feeds every package, and `logging_install/src/` feeds `integration_quickstart`), which is the usual source of missed rebuilds:

```bash
scripts/rebuild-dist.sh azure   # or: gcp, or no arg for both
git add azure/*/dist            # commit the rebuilt artifacts with your change
```

Better, enable the pre-commit hook once and it rebuilds + stages the affected `dist/` automatically on every commit:

```bash
git config core.hooksPath .githooks
```

(`azure/logging_install` needs the Azure CLI + bicep to rebuild its JSON; the hook skips the azure rebuild with a warning if they're not installed.)

To rebuild a single package instead, run its `build.sh` from the cloud parent directory (`cd azure && bash <package>/build.sh`).

## Test before pushing

```bash
cd <cloud>
python -m pytest <package>/tests
```

`shared/` and `agentless/` test suites depend on running from the cloud parent so the `pythonpath` in `pytest.ini` resolves shared modules.

## Release flow (informational)

Pushes to `main` that touch a package's source paths trigger `.github/workflows/release.yaml`:

1. `detect-changes` decides which packages changed.
2. Each affected package gets a versioned GitHub Release auto-published, tag format `<cloud>-<package>-vX.Y.Z`. The patch version auto-increments from the prior tag.
3. Asset URL: `https://github.com/DataDog/integrations-management/releases/download/<cloud>-<package>-vX.Y.Z/<file>.pyz`.

You don't need to do anything manually for releases — just follow the build-before-pushing rule above. Manual intervention only:

- Major/minor bumps: create the tag manually (e.g. `gcp-agentless-v0.2.0`) before merging the PR.
- Re-release everything from current main: `workflow_dispatch` on the Release workflow.

## What to avoid

- Don't edit files in `dist/` directly. They are build outputs.
- Don't commit `__pycache__/`, `.ruff_cache/`, or `.DS_Store` into `src/`. The build scripts strip these from the zipapp, but they shouldn't be in source either.
- Don't bypass the build step. CI will catch it but it wastes a round trip.
