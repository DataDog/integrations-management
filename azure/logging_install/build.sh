#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

rm -rf logging_install/dist/tmp
mkdir -p logging_install/dist/tmp
cp -r shared/src/. logging_install/dist/tmp
cp -r logging_install/src/. logging_install/dist/tmp
find logging_install/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find logging_install/dist/tmp -name .DS_Store -delete
python -m zipapp logging_install/dist/tmp \
  -o logging_install/dist/azure_logging_install.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_logging_install.main:main"
chmod +x logging_install/dist/azure_logging_install.pyz
rm -r logging_install/dist/tmp

BICEP_VERSION="v0.40.2"
if [[ "$(az bicep version 2>/dev/null | grep -oE 'version [0-9.]+' | awk '{print "v"$2}')" != "$BICEP_VERSION" ]]; then
  az bicep install --version "$BICEP_VERSION"
fi

az bicep build --file logging_install/bicep/azuredeploy.bicep --outfile logging_install/dist/azuredeploy.json
az bicep build --file logging_install/bicep/forwarder.bicep --outfile logging_install/dist/forwarder.json
cp logging_install/bicep/createUiDefinition.json logging_install/dist/createUiDefinition.json
