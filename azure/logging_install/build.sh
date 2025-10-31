# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf logging_install/dist/tmp
mkdir -p logging_install/dist/tmp
cp -r shared/src/. logging_install/dist/tmp
cp -r logging_install/src/. logging_install/dist/tmp
python -m zipapp logging_install/dist/tmp \
  -o logging_install/dist/azure_logging_install.pyz \
  -p "/usr/bin/env python3" \
  -m "azure_logging_install.main:main"
chmod +x logging_install/dist/azure_logging_install.pyz
rm -r logging_install/dist/tmp

az bicep build --file logging_install/bicep/azuredeploy.bicep --outfile logging_install/dist/azuredeploy.json
cp logging_install/bicep/createUiDefinition.json logging_install/dist/createUiDefinition.json
