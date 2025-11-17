from collections.abc import Iterable
from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.scopes import Scope


def scopes_equal(scope1: Scope, scope2: Scope):
    return (
        scope1.id == scope2.id
        and scope1.name == scope2.name
        and scope1.scope == scope2.scope
        and scope1.scope_type == scope2.scope_type
    )


class DDTestCase(TestCase):
    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_same_scopes(self, scopes1: Iterable[Scope], scopes2: Iterable[Scope]):
        return all([any([scopes_equal(scope1, scope2) for scope2 in scopes2]) for scope1 in scopes1])
