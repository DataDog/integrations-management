# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_integration_quickstart.util import UnionContainer, compile_wildcard


class TestUnionContainer(TestCase):
    def test_contains_empty(self):
        union_container: UnionContainer[str] = UnionContainer([[], ()])
        self.assertEqual("" in union_container, False)

    def test_contains_one(self):
        union_container = UnionContainer([["a", "b", "c"], ("d", "e", "f")])
        self.assertEqual("b" in union_container, True)
        self.assertEqual("e" in union_container, True)

    def test_contains_multiple(self):
        union_container = UnionContainer([["a", "b", "c"], ("c", "d", "e"), {"f", "g", "h"}])
        self.assertEqual("c" in union_container, True)

    def test_contains_none(self):
        union_container = UnionContainer([["a", "b", "c"], ("c", "d", "e"), {"g", "h", "i"}])
        self.assertEqual("f" in union_container, False)


class TestCompileWildcard(TestCase):
    def test_empty(self):
        regex = compile_wildcard("")
        self.assertEqual(regex.pattern, "^$")

    def test_no_wildcard(self):
        regex = compile_wildcard("colou?r")
        self.assertEqual(regex.pattern, "^colou\\?r$")

    def test_one_wildcard(self):
        regex = compile_wildcard("action_name:*")
        self.assertEqual(regex.pattern, "^action_name:.*$")

    def test_multiple_wildcard(self):
        regex = compile_wildcard("action_name:* action_id:*")
        self.assertEqual(regex.pattern, "^action_name:.*\\ action_id:.*$")
