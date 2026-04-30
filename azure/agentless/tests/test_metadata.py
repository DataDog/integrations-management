# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.


import pytest

from azure_agentless_setup.config import Config
from azure_agentless_setup.errors import MetadataError
from azure_agentless_setup.metadata import (
    DeploymentMetadata,
    merge_with_config,
)


def _make_config(**overrides) -> Config:
    defaults = dict(
        api_key="key",
        app_key="app",
        site="datadoghq.com",
        workflow_id="wf",
        scanner_subscription="sub-scanner",
        locations=["eastus"],
        subscriptions_to_scan=["sub-scanner", "sub-a"],
        resource_group="rg",
    )
    defaults.update(overrides)
    return Config(**defaults)


class TestDeploymentMetadata:
    def test_roundtrip(self):
        meta = DeploymentMetadata(
            scanner_subscription="sub-1",
            locations=["eastus", "westeurope"],
            subscriptions_to_scan=["sub-1", "sub-2"],
            created_at="2025-01-01T00:00:00",
            modified_at="2025-01-02T00:00:00",
        )
        d = meta.to_dict()
        restored = DeploymentMetadata.from_dict(d)

        assert restored.scanner_subscription == "sub-1"
        assert restored.locations == sorted(["eastus", "westeurope"])
        assert restored.subscriptions_to_scan == sorted(["sub-1", "sub-2"])

    def test_sorts_lists(self):
        meta = DeploymentMetadata(
            scanner_subscription="sub",
            locations=["westeurope", "eastus"],
            subscriptions_to_scan=["sub-b", "sub-a"],
            created_at="",
            modified_at="",
        )
        d = meta.to_dict()
        assert d["locations"] == ["eastus", "westeurope"]
        assert d["subscriptions_to_scan"] == ["sub-a", "sub-b"]


class TestMergeWithConfig:
    def test_new_deployment(self):
        config = _make_config(locations=["eastus"], subscriptions_to_scan=["sub-scanner", "sub-a"])
        result = merge_with_config(None, config)

        assert result.scanner_subscription == "sub-scanner"
        assert "eastus" in result.locations
        assert "sub-scanner" in result.subscriptions_to_scan
        assert "sub-a" in result.subscriptions_to_scan

    def test_additive_locations(self):
        existing = DeploymentMetadata(
            scanner_subscription="sub-scanner",
            locations=["eastus"],
            subscriptions_to_scan=["sub-scanner"],
            created_at="t0",
            modified_at="t0",
        )
        config = _make_config(locations=["westeurope"])
        result = merge_with_config(existing, config)

        assert "eastus" in result.locations
        assert "westeurope" in result.locations

    def test_additive_subscriptions(self):
        existing = DeploymentMetadata(
            scanner_subscription="sub-scanner",
            locations=["eastus"],
            subscriptions_to_scan=["sub-scanner", "sub-a"],
            created_at="t0",
            modified_at="t0",
        )
        config = _make_config(subscriptions_to_scan=["sub-scanner", "sub-b"])
        result = merge_with_config(existing, config)

        assert "sub-a" in result.subscriptions_to_scan
        assert "sub-b" in result.subscriptions_to_scan
        assert "sub-scanner" in result.subscriptions_to_scan

    def test_preserves_created_at(self):
        existing = DeploymentMetadata(
            scanner_subscription="sub-scanner",
            locations=["eastus"],
            subscriptions_to_scan=["sub-scanner"],
            created_at="original-time",
            modified_at="old-time",
        )
        config = _make_config()
        result = merge_with_config(existing, config)

        assert result.created_at == "original-time"
        assert result.modified_at != "old-time"

    def test_subscription_mismatch_raises(self):
        existing = DeploymentMetadata(
            scanner_subscription="sub-other",
            locations=["eastus"],
            subscriptions_to_scan=["sub-other"],
            created_at="t0",
            modified_at="t0",
        )
        config = _make_config(scanner_subscription="sub-scanner")

        with pytest.raises(MetadataError) as exc:
            merge_with_config(existing, config)

        assert "mismatch" in exc.value.message.lower()

    def test_deduplicates(self):
        existing = DeploymentMetadata(
            scanner_subscription="sub-scanner",
            locations=["eastus", "westeurope"],
            subscriptions_to_scan=["sub-scanner", "sub-a"],
            created_at="t0",
            modified_at="t0",
        )
        config = _make_config(
            locations=["eastus", "southeastasia"],
            subscriptions_to_scan=["sub-scanner", "sub-a"],
        )
        result = merge_with_config(existing, config)

        assert result.locations == sorted(["eastus", "southeastasia", "westeurope"])
        assert len(set(result.subscriptions_to_scan)) == len(result.subscriptions_to_scan)
