---
description: Build, test, and verify dist/ is in sync for any packages with pending changes. Run before pushing.
---

You are validating that pending changes in this branch are ready to push, specifically that the committed `dist/` artifacts match the current `src/`. This is the same check CI's `dist drift` job runs, but local — fail fast before the push.

## Steps

1. Identify which packages have pending changes.

   Run `git diff --name-only origin/main...HEAD` (and `git status -s` for unstaged/uncommitted changes). Map changed paths to packages:

   - Anything under `<cloud>/<package>/src/` or `<cloud>/<package>/build.sh` → that package.
   - Anything under `<cloud>/shared/src/` → all packages in that cloud.
   - Anything under `azure/logging_install/src/` → also `azure/integration_quickstart` (its `build.sh` bundles `logging_install/src/`).
   - Anything under `azure/logging_install/bicep/` → `azure/logging_install` (compiled to JSON).
   - Anything under `<cloud>/dev_requirements.txt` → all packages in that cloud.

2. For each affected package, run its build from the cloud parent directory:

   ```bash
   cd <cloud>
   bash <package>/build.sh
   ```

3. For each affected package, run its tests:

   ```bash
   cd <cloud>
   python -m pytest <package>/tests
   ```

   If `shared/src/` changed, also run `python -m pytest shared/tests` from the cloud parent.

4. Check whether `dist/` files are dirty (i.e. the build produced different output than what's committed):

   ```bash
   git status -s -- '<cloud>/<package>/dist/'
   ```

   If `dist/` files are modified, commit them alongside the source changes. They MUST be in the same commit chain — CI rejects PRs where `dist/` is out of sync with `src/`.

5. Report status to the user. For each affected package, one of:

   - ✅ build clean, tests pass, `dist/` already committed.
   - ⚠️  `dist/` was rebuilt and modified — needs to be committed before push.
   - ❌ build failed or tests failed — investigate before pushing.

## What this command does NOT do

- It does not push. The user pushes when they're ready.
- It does not bump release versions. The release workflow auto-bumps on merge to `main`.
- It does not fix lint or formatting. Run `ruff check --fix <cloud>` separately if needed.
