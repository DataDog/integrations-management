# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_integration_quickstart.permissions import Permission, flatten_permissions

action_all_read = "*/read"
action_vm_read = "Microsoft.Compute/virtualMachines/read"
action_vm_all = "Microsoft.Compute/virtualMachines/*"
action_resource_tags_write = "Microsoft.Resources/tags/write"


class TestPermissions(TestCase):
    def test_actions_single_permission(self):
        self.assertIn(
            action_all_read,
            flatten_permissions([Permission(actions=[action_all_read, action_vm_all])]).actions,
        )
        self.assertIn(
            action_vm_read,
            flatten_permissions([Permission(actions=[action_all_read, action_vm_all])]).actions,
        )
        self.assertNotIn(
            action_resource_tags_write,
            flatten_permissions([Permission(actions=[action_all_read, action_vm_all])]).actions,
        )

    def test_not_actions_single_permission(self):
        self.assertIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(
                        actions=[action_all_read, action_vm_all],
                        notActions=[action_resource_tags_write],
                    )
                ]
            ).actions,
        )
        self.assertNotIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(
                        actions=[action_all_read, action_vm_all],
                        notActions=[action_vm_read],
                    )
                ]
            ).actions,
        )

    def test_not_actions_partial_overlap(self):
        self.assertNotIn(
            action_all_read,
            flatten_permissions(
                [Permission(actions=[action_all_read, action_vm_all], notActions=[action_vm_read])]
            ).actions,
        )

    def test_not_actions_full_overlap(self):
        self.assertNotIn(
            action_vm_read,
            flatten_permissions(
                [
                    Permission(
                        actions=[action_all_read, action_vm_all],
                        notActions=[action_all_read],
                    )
                ]
            ).actions,
        )

    def test_actions_multi_permission(self):
        self.assertIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(actions=[action_all_read]),
                    Permission(actions=[action_vm_all], notActions=[]),
                ]
            ).actions,
        )
        self.assertIn(
            action_vm_read,
            flatten_permissions([Permission(actions=[action_all_read]), Permission(actions=[action_vm_all])]).actions,
        )
        self.assertNotIn(
            action_resource_tags_write,
            flatten_permissions([Permission(actions=[action_all_read]), Permission(actions=[action_vm_all])]).actions,
        )

    def test_not_actions_multi_permission(self):
        self.assertIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(actions=[action_all_read, action_vm_all], notActions=[action_resource_tags_write]),
                    Permission(notActions=[action_resource_tags_write]),
                ]
            ).actions,
        )
        self.assertNotIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(actions=[action_all_read, action_vm_all], notActions=[action_vm_read]),
                    Permission(notActions=[action_vm_read]),
                ]
            ).actions,
        )

    def test_permissions_always_additive(self):
        """One permission's not_action cannot revoke another permission's action."""
        self.assertNotIn(
            action_all_read,
            flatten_permissions(
                [
                    Permission(actions=[action_all_read, action_vm_all], notActions=[action_vm_read]),
                    Permission(actions=[action_vm_read]),
                ]
            ).actions,
        )
