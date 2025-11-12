# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Shared test data constants for azure's shared util tests."""

CONTROL_PLANE_SUBSCRIPTION_ID = "cp-sub-id"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"

EXAMPLE_POLICY_NAME = "Example policy name"
EXAMPLE_POLICY_ERROR = """Resource 'dd-log-forwarder-env-00000000-eastus' was disallowed by policy. Policy identifiers: '[{"policyAssignment":{"name":"Example policy assignment","id":"/providers/Microsoft.Management/managementGroups/mgroup1/providers/Microsoft.Authorization/policyAssignments/1111111"},"policyDefinition":{"name":"Example policy name","id":"/providers/Microsoft.Authorization/policyDefinitions/222222222222222","version":"1.1.0"},"policySetDefinition":{"name":"Example policy set","id":"/providers/Microsoft.Management/managementGroups/SomeMGroup/providers/Microsoft.Authorization/policySetDefinitions/333333333333333333","version":"1.0.0"}}]'."""
