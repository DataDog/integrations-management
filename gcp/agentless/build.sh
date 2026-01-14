# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf agentless/dist/tmp
mkdir -p agentless/dist/tmp
cp -r shared/src/. agentless/dist/tmp
cp -r agentless/src/. agentless/dist/tmp
python -m zipapp agentless/dist/tmp \
  -o agentless/dist/gcp_agentless_setup.pyz \
  -p "/usr/bin/env python3" \
  -m "gcp_agentless_setup.main:main"
chmod +x agentless/dist/gcp_agentless_setup.pyz
rm -r agentless/dist/tmp

