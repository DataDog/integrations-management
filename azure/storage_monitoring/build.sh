#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

BICEP_VERSION="v0.40.2"
if [[ "$(az bicep version 2>/dev/null | grep -oE 'version [0-9.]+' | awk '{print "v"$2}')" != "$BICEP_VERSION" ]]; then
  az bicep install --version "$BICEP_VERSION"
fi

az bicep build --file storage_monitoring/bicep/azuredeploy.bicep --outfile storage_monitoring/dist/azuredeploy.json
