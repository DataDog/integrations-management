#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

rm -rf mwaa/dist/tmp
mkdir -p mwaa/dist/tmp
cp -r shared/src/. mwaa/dist/tmp
cp -r mwaa/src/. mwaa/dist/tmp

find mwaa/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find mwaa/dist/tmp -name .DS_Store -delete

python -m zipapp mwaa/dist/tmp \
  -o mwaa/dist/mwaa.pyz \
  -p "/usr/bin/env python3" \
  -m "mwaa.main:main"
chmod +x mwaa/dist/mwaa.pyz

rm -r mwaa/dist/tmp
