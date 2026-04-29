#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

# Check if rebuild is needed (skip if no source files changed)
if [[ -f agentless/dist/azure_agentless_setup.pyz ]] && \
   [[ -z $(find shared/src agentless/src -newer agentless/dist/azure_agentless_setup.pyz 2>/dev/null) ]]; then
  echo "No changes detected, skipping build."
  exit 0
fi

echo "Building azure_agentless_setup.pyz..."

rm -rf agentless/dist/tmp

mkdir -p agentless/dist/tmp
cp -r shared/src/. agentless/dist/tmp
cp -r agentless/src/. agentless/dist/tmp

find agentless/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find agentless/dist/tmp -name .DS_Store -delete

if python -m zipapp agentless/dist/tmp \
  -o agentless/dist/azure_agentless_setup.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_agentless_setup.main:main"; then

  chmod +x agentless/dist/azure_agentless_setup.pyz
  rm -r agentless/dist/tmp

  echo "✅ Build successful: agentless/dist/azure_agentless_setup.pyz"
else
  rm -rf agentless/dist/tmp
  echo "❌ Build failed"
  exit 1
fi
