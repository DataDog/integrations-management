# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf integration_quickstart/dist/tmp
mkdir -p integration_quickstart/dist/tmp
cp -r integration_quickstart/src/. integration_quickstart/dist/tmp
cp -r logging_install/src/. integration_quickstart/dist/tmp
cp -r shared/src/. integration_quickstart/dist/tmp

# Build app registration quickstart executable
python -m zipapp integration_quickstart/dist/tmp \
  -o integration_quickstart/dist/azure_app_registration_quickstart.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_integration_quickstart.app_registration_quickstart:main"
chmod +x integration_quickstart/dist/azure_app_registration_quickstart.pyz

# Build log forwarding quickstart executable
python -m zipapp integration_quickstart/dist/tmp \
  -o integration_quickstart/dist/azure_log_forwarding_quickstart.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_integration_quickstart.log_forwarding_quickstart:main"
chmod +x integration_quickstart/dist/azure_log_forwarding_quickstart.pyz

rm -r integration_quickstart/dist/tmp
