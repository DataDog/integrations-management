#!/usr/bin/env bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

# Rebuild the committed dist/ artifacts from src/ so they match source.
#
# Usage: scripts/rebuild-dist.sh [azure|gcp ...]   (default: both clouds)
#
# dist/ artifacts (the bundled *.pyz and, for azure/logging_install, the
# bicep-compiled *.json) are committed and MUST match src/. Editing shared or
# otherwise-bundled source silently invalidates every package that bundles it,
# so this rebuilds all of a cloud's packages at once. CI's "dist drift" job
# enforces the match. azure/logging_install also needs the Azure CLI + bicep.
set -euo pipefail
shopt -s nullglob

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

clouds=("$@")
if [[ ${#clouds[@]} -eq 0 ]]; then
  clouds=(azure gcp)
fi

for cloud in "${clouds[@]}"; do
  cloud_dir="$repo_root/$cloud"
  if [[ ! -d "$cloud_dir" ]]; then
    echo "error: unknown cloud '$cloud' (expected 'azure' or 'gcp')" >&2
    exit 2
  fi
  echo "==> rebuilding $cloud dist"
  cd "$cloud_dir"
  # agentless/build.sh short-circuits when its .pyz is newer than src; delete
  # first to force a clean rebuild, matching CI's drift check.
  find */dist -name '*.pyz' -delete
  for build in */build.sh; do
    echo "  - $build"
    bash "$build"
  done
done

echo "✅ dist rebuilt for: ${clouds[*]}"
