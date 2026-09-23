from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_tool_dispatch_custom_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.identity import Tenant
from app.models.integrations import TenantIntegrationEvent
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.services.tool_dispatch_service import (
    ToolArgumentError,
    ToolDispatchService,
    ToolExecutionError,
    ToolNotAvailableError,
    ToolNotFoundError,
)
from app.services.tool_http_safety import SafeHttpClient
from app.services.tenant_feature_service import CUSTOM_HTTP_TOOLS, TenantFeatureService
from app.services.voice_session_service import VoiceSessionService


def _addrinfo(ip: str) -> list[tuple]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class ToolDispatchCustomToolsTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            self.tenant = Tenant(name="Tenant A", slug="tenant-a")
            self.other_tenant = Tenant(name="Tenant B", slug="tenant-b")
            db.add_all([self.tenant, self.other_tenant])
            db.commit()
            db.refresh(self.tenant)
            db.refresh(self.other_tenant)
            self.tenant_id = self.tenant.id
            self.other_tenant_id = self.other_tenant.id
            TenantFeatureService(db).set_feature(
                self.tenant_id, CUSTOM_HTTP_TOOLS, True, {}, None
            )
            TenantFeatureService(db).set_feature(
                self.other_tenant_id, CUSTOM_HTTP_TOOLS, True, {}, None
            )

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _create_custom_tool(
        self,
        db,
        tenant_id,
        *,
        key="custom.customer_balance",
        status="active",
        response_mapping=None,
    ) -> TenantTool:
        tool = TenantTool(
            tenant_id=tenant_id, key=key, name="Consultar saldo", description="...", status=status
        )
        db.add(tool)
        db.commit()
        db.refresh(tool)
        config = TenantHttpToolConfig(
            tenant_id=tenant_id,
            tenant_tool_id=tool.id,
            method="GET",
            base_url="https://example-api.test",
            path_template="/customers/{document}/balance",
            headers_json={},
            path_mapping_json={"document": "args.document"},
            query_mapping_json={},
            body_mapping_json={},
            input_schema_json={
                "type": "object",
                "properties": {"document": {"type": "string"}},
                "required": ["document"],
            },
            response_mapping_json=response_mapping or {},
        )
        db.add(config)
        db.commit()
        return tool

    def _create_session(self, db, tenant_id, tool_key, *, enabled=True) -> str:
        agent = TenantAgent(tenant_id=tenant_id, name="Agent", status="draft")
        db.add(agent)
        db.flush()
        version = TenantAgentVersion(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            status="published",
            language="es",
            timezone="America/Bogota",
            identity_json={},
            instructions_json={},
            behavior_json={},
            runtime_binding_json={
                "pipeline_type": "realtime",
                "realtime": {"provider": "ultravox", "model": "x", "management_mode": "serviglobal_managed"},
                "tools": [{"key": tool_key, "enabled": enabled, "config": {}}],
            },
        )
        db.add(version)
        db.flush()
        agent.status = "active"
        agent.published_version_id = version.id
        db.commit()
        session = VoiceSessionService(db).create(tenant_id, agent.id, channel="webrtc", direction="internal")
        db.commit()
        return session.id

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_full_lifecycle_returns_mapped_result(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/customers/79123456/balance"))
            return httpx.Response(
                200, json={"billing": {"balance": 4500}}, headers={"content-type": "application/json"}
            )

        transport = httpx.MockTransport(handler)

        with SessionLocal() as db:
            tool = self._create_custom_tool(
                db, self.tenant_id, response_mapping={"balance": "response.billing.balance"}
            )
            session_id = self._create_session(db, self.tenant_id, tool.key)

        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                result = ToolDispatchService(db).invoke(session_id, tool.key, {"document": "79123456"})
        self.assertEqual(result, {"balance": 4500})

    def test_disabled_binding_raises_not_found(self):
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key, enabled=False)
        with SessionLocal() as db:
            with self.assertRaises(ToolNotFoundError):
                ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    def test_disabled_tool_status_wins_over_enabled_binding(self):
        """DB-level tool state always wins over stale binding state -- a
        tool disabled after the agent was published must stop executing
        even though the (now stale) binding still says enabled."""
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id, status="disabled")
            session_id = self._create_session(db, self.tenant_id, tool.key, enabled=True)
        with SessionLocal() as db:
            with self.assertRaises(ToolNotAvailableError):
                ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    def test_cross_tenant_tool_never_executes(self):
        with SessionLocal() as db:
            self._create_custom_tool(db, self.other_tenant_id, key="custom.customer_balance")
            session_id = self._create_session(db, self.tenant_id, "custom.customer_balance")
        with SessionLocal() as db:
            with self.assertRaises(ToolNotAvailableError):
                ToolDispatchService(db).invoke(session_id, "custom.customer_balance", {"document": "1"})

    def test_argument_validation_error(self):
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with self.assertRaises(ToolArgumentError):
                ToolDispatchService(db).invoke(session_id, tool.key, {})

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_upstream_5xx_raises_tool_execution_error(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"}, headers={"content-type": "application/json"})

        transport = httpx.MockTransport(handler)
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                with self.assertRaises(ToolExecutionError):
                    ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_upstream_4xx_raises_tool_execution_error(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                401, json={"error": "unauthorized"}, headers={"content-type": "application/json"}
            )
        )
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                with self.assertRaises(ToolExecutionError):
                    ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    def test_revoked_feature_stops_published_tool_execution(self):
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
            TenantFeatureService(db).set_feature(self.tenant_id, CUSTOM_HTTP_TOOLS, False, {}, None)
        with SessionLocal() as db:
            with self.assertRaises(ToolNotAvailableError):
                ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    def test_declared_integer_argument_rejects_string(self):
        with self.assertRaises(ToolArgumentError):
            ToolDispatchService._validate_arguments(
                {"type": "object", "properties": {"amount": {"type": "integer"}}},
                {"amount": "not-a-number"},
            )

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_oversized_response_raises_tool_execution_error(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")
        oversized = b"x" * (1_048_576 + 1)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=oversized, headers={"content-type": "text/plain"})

        transport = httpx.MockTransport(handler)
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                with self.assertRaises(ToolExecutionError):
                    ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_disallowed_content_type_raises_tool_execution_error(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, html="<html></html>", headers={"content-type": "text/html"})

        transport = httpx.MockTransport(handler)
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                with self.assertRaises(ToolExecutionError):
                    ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_ssrf_target_raises_tool_execution_error(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("10.0.0.5")
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with self.assertRaises(ToolExecutionError):
                ToolDispatchService(db).invoke(session_id, tool.key, {"document": "1"})

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_audit_event_never_contains_endpoint_or_arguments(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"balance": 1}, headers={"content-type": "application/json"})

        transport = httpx.MockTransport(handler)
        with SessionLocal() as db:
            tool = self._create_custom_tool(db, self.tenant_id)
            session_id = self._create_session(db, self.tenant_id, tool.key)
        with SessionLocal() as db:
            with patch("app.services.custom_http_tool_executor.SafeHttpClient") as mock_cls:
                mock_cls.return_value = SafeHttpClient(transport=transport)
                ToolDispatchService(db).invoke(session_id, tool.key, {"document": "79123456"})
        with SessionLocal() as db:
            events = (
                db.query(TenantIntegrationEvent).filter_by(event_type="agent_tool_invoked").all()
            )
            self.assertTrue(events)
            for event in events:
                dumped = str(event.metadata_json)
                self.assertNotIn("79123456", dumped)
                self.assertNotIn("example-api.test", dumped)


if __name__ == "__main__":
    unittest.main()
