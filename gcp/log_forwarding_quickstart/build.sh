# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf log_forwarding_quickstart/dist/tmp
mkdir -p log_forwarding_quickstart/dist/tmp
cp -r shared/src/. log_forwarding_quickstart/dist/tmp
cp -r log_forwarding_quickstart/src/. log_forwarding_quickstart/dist/tmp
python -m zipapp log_forwarding_quickstart/dist/tmp \
  -o log_forwarding_quickstart/dist/gcp_log_forwarding_quickstart.pyz \
  -p "/usr/bin/env python3" \
  -m "gcp_log_forwarding_quickstart.main:main"
chmod +x log_forwarding_quickstart/dist/gcp_log_forwarding_quickstart.pyz
rm -r log_forwarding_quickstart/dist/tmp

