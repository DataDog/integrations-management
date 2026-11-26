#!/bin/bash
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# Copyright 2026 Datadog, Inc.
# Compatibility entry point. Keep setup.py alongside this file.
set -euo pipefail
exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/setup.py" "$@"
