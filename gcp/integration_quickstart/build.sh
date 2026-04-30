#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

rm -rf integration_quickstart/dist/tmp
mkdir -p integration_quickstart/dist/tmp
cp -r shared/src/. integration_quickstart/dist/tmp
cp -r integration_quickstart/src/. integration_quickstart/dist/tmp
find integration_quickstart/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find integration_quickstart/dist/tmp -name .DS_Store -delete
python -m zipapp integration_quickstart/dist/tmp \
  -o integration_quickstart/dist/gcp_integration_quickstart.pyz \
  -p "/usr/bin/env python3" \
  -m "gcp_integration_quickstart.main:main"
chmod +x integration_quickstart/dist/gcp_integration_quickstart.pyz
rm -r integration_quickstart/dist/tmp