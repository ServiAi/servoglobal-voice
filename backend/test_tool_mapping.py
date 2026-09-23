from __future__ import annotations

import unittest

from app.domain.tool_mapping import (
    MappingPathError,
    build_path,
    build_request_values,
    extract_response_values,
    resolve_path,
)


class ToolMappingTests(unittest.TestCase):
    def setUp(self):
        self.args = {"document": "79123456", "date": "2026-09-22"}
        self.context = {"caller": {"phone": "+573001234567"}, "lead": {"id": "lead-1"}}
        self.binding_config = {"region": "co"}

    def test_args_root_resolves(self):
        values = build_request_values({"doc": "args.document"}, args=self.args, context=self.context, binding_config=self.binding_config)
        self.assertEqual(values, {"doc": "79123456"})

    def test_context_root_resolves_nested_path(self):
        values = build_request_values(
            {"phone": "context.caller.phone"}, args=self.args, context=self.context, binding_config=self.binding_config
        )
        self.assertEqual(values, {"phone": "+573001234567"})

    def test_binding_root_resolves_config(self):
        values = build_request_values(
            {"region": "binding.config.region"}, args=self.args, context=self.context, binding_config=self.binding_config
        )
        self.assertEqual(values, {"region": "co"})

    def test_unknown_root_is_rejected(self):
        with self.assertRaises(MappingPathError):
            build_request_values(
                {"x": "secret.api_key"}, args=self.args, context=self.context, binding_config=self.binding_config
            )

    def test_env_style_root_is_rejected(self):
        with self.assertRaises(MappingPathError):
            build_request_values(
                {"x": "env.HOME"}, args=self.args, context=self.context, binding_config=self.binding_config
            )

    def test_missing_source_path_produces_controlled_error(self):
        with self.assertRaises(MappingPathError):
            build_request_values(
                {"x": "args.does_not_exist"}, args=self.args, context=self.context, binding_config=self.binding_config
            )

    def test_request_side_rejects_list_index(self):
        args = {"items": ["a", "b"]}
        with self.assertRaises(MappingPathError):
            build_request_values({"x": "args.items.0"}, args=args, context={}, binding_config={})

    def test_path_depth_cap(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": "too deep"}}}}}}}}}
        with self.assertRaises(MappingPathError):
            resolve_path(deep, "a.b.c.d.e.f.g.h.i", allow_list_index=False)

    def test_response_mapping_numeric_index_resolves(self):
        response = {"results": [{"balance": 1000}, {"balance": 2000}]}
        values = extract_response_values({"balance": "response.results.0.balance"}, response)
        self.assertEqual(values, {"balance": 1000})

    def test_response_mapping_rejects_wildcard(self):
        response = {"items": [1, 2, 3]}
        with self.assertRaises(MappingPathError):
            extract_response_values({"x": "response.items[*]"}, response)

    def test_response_mapping_rejects_slice(self):
        response = {"items": [1, 2, 3]}
        with self.assertRaises(MappingPathError):
            extract_response_values({"x": "response.items[0:2]"}, response)

    def test_response_mapping_index_out_of_range(self):
        response = {"items": [1]}
        with self.assertRaises(MappingPathError):
            extract_response_values({"x": "response.items.5"}, response)

    def test_build_path_resolves_placeholder(self):
        path = build_path(
            "/customers/{document}/balance",
            {"document": "args.document"},
            args=self.args,
            context=self.context,
            binding_config=self.binding_config,
        )
        self.assertEqual(path, "/customers/79123456/balance")

    def test_build_path_url_encodes_value(self):
        path = build_path(
            "/lookup/{code}",
            {"code": "args.code"},
            args={"code": "a/b c"},
            context={},
            binding_config={},
        )
        self.assertEqual(path, "/lookup/a%2Fb%20c")

    def test_build_path_rejects_unresolved_placeholder(self):
        with self.assertRaises(MappingPathError):
            build_path(
                "/customers/{document}/{missing}",
                {"document": "args.document"},
                args=self.args,
                context=self.context,
                binding_config=self.binding_config,
            )

    def test_response_mapping_top_level_object(self):
        response = {"balance": 4500, "due_date": "2026-09-30"}
        values = extract_response_values(
            {"balance": "response.balance", "due_date": "response.due_date"}, response
        )
        self.assertEqual(values, {"balance": 4500, "due_date": "2026-09-30"})


if __name__ == "__main__":
    unittest.main()
