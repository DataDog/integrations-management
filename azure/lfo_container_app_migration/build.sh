#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

rm -rf lfo_container_app_migration/dist/tmp
mkdir -p lfo_container_app_migration/dist/tmp
cp -r lfo_container_app_migration/src/. lfo_container_app_migration/dist/tmp
cp -r logging_install/src/. lfo_container_app_migration/dist/tmp
cp -r shared/src/. lfo_container_app_migration/dist/tmp

find lfo_container_app_migration/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find lfo_container_app_migration/dist/tmp -name .DS_Store -delete

python -m zipapp lfo_container_app_migration/dist/tmp \
  -o lfo_container_app_migration/dist/azure_lfo_container_app_migration.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_lfo_container_app_migration.main:main"
chmod +x lfo_container_app_migration/dist/azure_lfo_container_app_migration.pyz

rm -r lfo_container_app_migration/dist/tmp
