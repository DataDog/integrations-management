# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

rm -rf issue_resolver/dist/tmp
mkdir -p issue_resolver/dist/tmp
cp -r shared/src/. issue_resolver/dist/tmp
cp -r issue_resolver/src/. issue_resolver/dist/tmp
python -m zipapp issue_resolver/dist/tmp \
  -o issue_resolver/dist/gcp_issue_resolver.pyz \
  -p "/usr/bin/env python3" \
  -m "gcp_issue_resolver.main:main"
chmod +x issue_resolver/dist/gcp_issue_resolver.pyz
rm -r issue_resolver/dist/tmp


