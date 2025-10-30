# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf integration_quickstart/dist/tmp
mkdir -p integration_quickstart/dist/tmp
cp -r integration_quickstart/src/. integration_quickstart/dist/tmp
cp -r logging_install/src/. integration_quickstart/dist/tmp
cp -r shared/src/. integration_quickstart/dist/tmp
python -m zipapp integration_quickstart/dist/tmp \
  -o integration_quickstart/dist/azure_integration_quickstart.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_integration_quickstart.main:main"
chmod +x integration_quickstart/dist/azure_integration_quickstart.pyz
rm -r integration_quickstart/dist/tmp