#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

set -e

PKG=lfo_linux_consumption_plan_migraiton
OUT=$PKG/dist/azure_lfo_consumption_plan_migration.pyz

if [[ -f $OUT ]] && \
   [[ -z $(find shared/src $PKG/src -newer $OUT 2>/dev/null) ]]; then
  echo "No changes detected, skipping build."
  exit 0
fi

echo "Building $OUT..."

rm -rf $PKG/dist/tmp
mkdir -p $PKG/dist/tmp
cp -r shared/src/. $PKG/dist/tmp
cp -r $PKG/src/. $PKG/dist/tmp

find $PKG/dist/tmp \( -name __pycache__ -o -name .ruff_cache \) -type d -exec rm -rf {} +
find $PKG/dist/tmp -name .DS_Store -delete

if python -m zipapp $PKG/dist/tmp \
  -o $OUT \
  -p "/usr/bin/env python3" \
  -m "azure_lfo_consumption_plan_migration.main:main"; then

  chmod +x $OUT
  rm -r $PKG/dist/tmp

  echo "Build successful: $OUT"
else
  rm -rf $PKG/dist/tmp
  echo "Build failed"
  exit 1
fi
