from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.api.auth.deps import get_current_auth_context
from app.db.session import SessionLocal
from app.main import app
from app.models.integrations import TenantVoiceAgentConfig
from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService


class PublicVoiceExperienceTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent_id = self._seed_agent()
        self.schema_id = self._seed_schema("active", "public_schema")
        self._seed_fields(self.schema_id)
        self._set_feature(True)

    def _seed_agent(self, *, tenant_id: str | None = None, key: str = "public-agent") -> str:
        with SessionLocal() as db:
            agent = TenantVoiceAgentConfig(
                tenant_id=tenant_id or self.tenant.id,
                provider="ultravox",
                provider_agent_id=key,
                display_name="Private provider agent",
                default_system_prompt="never public",
                default_tools_json={"private": "tool"},
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            return agent.id

    def _seed_schema(
        self,
        status: str,
        key: str,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
    ) -> str:
        with SessionLocal() as db:
            schema = TenantVoiceContextSchema(
                tenant_id=tenant_id or self.tenant.id,
                agent_config_id=agent_id or self.agent_id,
                schema_key=key,
                version=1,
                status=status,
                name="Private schema name",
            )
            db.add(schema)
            db.commit()
            db.refresh(schema)
            return schema.id

    def _seed_fields(self, schema_id: str) -> None:
        definitions = [
            ("internal", "Internal secret", "text", "internal_only", 4, []),
            ("email", "Email", "email", "ask_if_missing", 2, []),
            (
                "plan",
                "Plan",
                "select",
                "prefill_and_confirm",
                0,
                [{"value": "pro", "label": "Pro"}],
            ),
            ("verified", "Verified", "checkbox", "trust_prefill", 1, []),
            ("during", "During call", "text", "collect_during_call", 3, []),
        ]
        with SessionLocal() as db:
            db.add_all(
                [
                    TenantVoiceContextField(
                        tenant_id=self.tenant.id,
                        schema_id=schema_id,
                        key=key,
                        label=label,
                        description=f"Description for {key}",
                        field_type=field_type,
                        collection_mode=mode,
                        required=key in {"email", "plan"},
                        position=position,
                        sensitivity="sensitive" if key == "email" else "standard",
                        validation_json={"private": True},
                        options_json=options,
                    )
                    for key, label, field_type, mode, position, options in definitions
                ]
            )
            db.commit()

    def _set_feature(self, enabled: bool, tenant_id: str | None = None) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id,
                VOICE_EXPERIENCES,
                enabled,
                {"max_experiences": 10, "max_context_fields": 10},
                self.user.id,
            )

    def _payload(
        self,
        *,
        title: str = "Published title",
        schema_id: str | None = None,
        name: str = "Public experience",
    ) -> dict:
        return {
            "agent_config_id": self.agent_id,
            "context_schema_id": schema_id or self.schema_id,
            "name": name,
            "default_locale": "es",
            "content": {
                "title": title,
                "description": "Published description",
                "submit_label": "Continue",
                "call_label": "Start call",
                "success_message": "Ready",
            },
            "theme": {
                "logo_url": "https://example.com/logo.png",
                "primary_color": "#123ABC",
                "layout": "card",
            },
            "consent": {
                "required": True,
                "label": "I accept",
                "privacy_url": "https://example.com/privacy",
            },
            "call_settings": {
                "auto_start": False,
                "show_microphone_help": True,
                "language": "es",
            },
        }

    def _create(self, **overrides) -> dict:
        response = self.client.post(
            "/api/v1/voice/experiences", json=self._payload(**overrides)
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _publish(self, **overrides) -> dict:
        created = self._create(**overrides)
        response = self.client.post(
            f"/api/v1/voice/experiences/{created['id']}/publish"
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _get(self, slug: str, suffix: str = ""):
        return self.client.get(
            f"/api/v1/public/voice-experiences/{slug}{suffix}"
        )

    def test_public_get_requires_no_auth_and_returns_sanitized_snapshot(self) -> None:
        published = self._publish()
        app.dependency_overrides.pop(get_current_auth_context, None)

        response = self._get(published["slug"])

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(
            response.json(),
            {
                "slug": published["slug"],
                "locale": "es",
                "version": 1,
                "content": {
                    "title": "Published title",
                    "description": "Published description",
                    "submit_label": "Continue",
                    "call_label": "Start call",
                    "success_message": "Ready",
                },
                "theme": {
                    "logo_url": "https://example.com/logo.png",
                    "primary_color": "#123ABC",
                    "background_color": None,
                    "color_scheme": "light",
                    "layout": "card",
                },
                "consent": {
                    "required": True,
                    "label": "I accept",
                    "privacy_url": "https://example.com/privacy",
                },
                "fields": [
                    {
                        "key": "plan",
                        "label": "Plan",
                        "description": "Description for plan",
                        "field_type": "select",
                        "required": True,
                        "options": [{"value": "pro", "label": "Pro"}],
                    },
                    {
                        "key": "verified",
                        "label": "Verified",
                        "description": "Description for verified",
                        "field_type": "checkbox",
                        "required": False,
                        "options": [],
                    },
                    {
                        "key": "email",
                        "label": "Email",
                        "description": "Description for email",
                        "field_type": "email",
                        "required": True,
                        "options": [],
                    },
                ],
                "call_settings": {
                    "auto_start": False,
                    "show_microphone_help": True,
                    "language": "es",
                    "mode": "webrtc",
                    "phone_field_key": None,
                    "default_country": "CO",
                    "allowed_countries": [],
                },
                "capabilities": {"submissions": True, "calls": True},
            },
        )

    def test_public_theme_dark_and_background_color_round_trip(self) -> None:
        payload = self._payload()
        payload["theme"]["color_scheme"] = "dark"
        payload["theme"]["background_color"] = "#0F172A"
        created = self.client.post(
            "/api/v1/voice/experiences", json=payload
        ).json()
        published = self.client.post(
            f"/api/v1/voice/experiences/{created['id']}/publish"
        ).json()
        app.dependency_overrides.pop(get_current_auth_context, None)

        theme = self._get(published["slug"]).json()["theme"]

        self.assertEqual(theme["color_scheme"], "dark")
        self.assertEqual(theme["background_color"], "#0F172A")

    def test_public_theme_backward_compatible_with_missing_color_scheme(self) -> None:
        published = self._publish()
        with SessionLocal() as db:
            version = db.scalar(
                select(TenantVoiceExperienceVersion).where(
                    TenantVoiceExperienceVersion.id == published["published_version_id"]
                )
            )
            legacy_theme = dict(version.theme_json)
            legacy_theme.pop("color_scheme", None)
            legacy_theme.pop("background_color", None)
            version.theme_json = legacy_theme
            db.commit()
        app.dependency_overrides.pop(get_current_auth_context, None)

        response = self._get(published["slug"])

        self.assertEqual(response.status_code, 200, response.text)
        theme = response.json()["theme"]
        self.assertEqual(theme["color_scheme"], "light")
        self.assertIsNone(theme["background_color"])

    def test_unknown_and_malformed_slugs_share_generic_404_and_no_store(self) -> None:
        for slug in ("unknown", "bad!slug", "a" * 65):
            with self.subTest(slug=slug[:10]):
                response = self._get(slug)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Not found"})
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_non_published_states_are_indistinguishable(self) -> None:
        for state in ("draft", "unpublished", "archived"):
            with self.subTest(state=state):
                experience = self._create(name=f"State {state}")
                if state == "unpublished":
                    self.client.post(
                        f"/api/v1/voice/experiences/{experience['id']}/publish"
                    )
                    self.client.post(
                        f"/api/v1/voice/experiences/{experience['id']}/unpublish"
                    )
                elif state == "archived":
                    self.client.post(
                        f"/api/v1/voice/experiences/{experience['id']}/archive"
                    )
                response = self._get(experience["slug"])
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Not found"})

    def test_published_without_reference_fails_closed(self) -> None:
        published = self._publish()
        with SessionLocal() as db:
            experience = db.get(TenantVoiceExperience, published["id"])
            experience.published_version_id = None
            db.commit()
        self.assertEqual(self._get(published["slug"]).status_code, 404)

    def test_inconsistent_version_reference_fails_closed(self) -> None:
        first = self._publish(name="First")
        second = self._publish(name="Second")
        with SessionLocal() as db:
            first_row = db.get(TenantVoiceExperience, first["id"])
            first_row.published_version_id = second["published_version_id"]
            db.commit()
        self.assertEqual(self._get(first["slug"]).status_code, 404)

    def test_disabled_feature_is_generic_404(self) -> None:
        published = self._publish()
        self._set_feature(False)
        response = self._get(published["slug"])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not found"})

    def test_public_response_uses_snapshot_not_mutable_draft(self) -> None:
        published = self._publish(title="Snapshot title")
        update = self.client.put(
            f"/api/v1/voice/experiences/{published['id']}",
            json=self._payload(title="Changed draft title"),
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(
            self._get(published["slug"]).json()["content"]["title"],
            "Snapshot title",
        )

    def test_unpublish_hides_immediately_and_republish_exposes_version_two(self) -> None:
        published = self._publish(title="Version one")
        self.client.post(f"/api/v1/voice/experiences/{published['id']}/unpublish")
        self.assertEqual(self._get(published["slug"]).status_code, 404)
        self.client.put(
            f"/api/v1/voice/experiences/{published['id']}",
            json=self._payload(title="Version two"),
        )
        self.client.post(f"/api/v1/voice/experiences/{published['id']}/publish")
        response = self._get(published["slug"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(response.json()["content"]["title"], "Version two")

    def test_archived_historical_schema_remains_public(self) -> None:
        published = self._publish()
        with SessionLocal() as db:
            db.get(TenantVoiceContextSchema, self.schema_id).status = "archived"
            db.commit()
        self.assertEqual(self._get(published["slug"]).status_code, 200)

    def test_historical_schema_comes_from_version_not_current_draft(self) -> None:
        published = self._publish()
        schema_b = self._seed_schema("active", "new_draft_schema")
        with SessionLocal() as db:
            db.add(
                TenantVoiceContextField(
                    tenant_id=self.tenant.id,
                    schema_id=schema_b,
                    key="leak",
                    label="Must not leak",
                    field_type="text",
                    collection_mode="ask_if_missing",
                    required=False,
                    position=0,
                    sensitivity="standard",
                    validation_json={},
                    options_json=[],
                )
            )
            db.commit()
        update = self.client.put(
            f"/api/v1/voice/experiences/{published['id']}",
            json=self._payload(schema_id=schema_b),
        )
        self.assertEqual(update.status_code, 200, update.text)
        labels = [field["label"] for field in self._get(published["slug"]).json()["fields"]]
        self.assertEqual(labels, ["Plan", "Verified", "Email"])

    def test_raw_response_excludes_internal_contract_and_hidden_fields(self) -> None:
        published = self._publish()
        raw = self._get(published["slug"]).text
        for forbidden in (
            "tenant_id",
            "experience_id",
            "agent_config_id",
            "context_schema_id",
            "published_version_id",
            "created_by_user_id",
            "published_by_user_id",
            "created_at",
            "updated_at",
            "sensitivity",
            "collection_mode",
            "validation_json",
            "provider",
            "api_key",
            "sip",
            "credential",
            "prompt",
            "tools",
            "Internal secret",
            "During call",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, raw)

    def test_tenant_id_query_and_get_body_do_not_change_resolution(self) -> None:
        published = self._publish()
        query_response = self._get(published["slug"], "?tenant_id=attacker")
        body_response = self.client.request(
            "GET",
            f"/api/v1/public/voice-experiences/{published['slug']}",
            json={"tenant_id": "attacker"},
        )
        self.assertEqual(query_response.status_code, 200)
        self.assertEqual(body_response.status_code, 200)
        self.assertEqual(query_response.json(), body_response.json())

    def test_missing_historical_schema_is_generic_404(self) -> None:
        published = self._publish()
        with SessionLocal() as db:
            version = db.get(
                TenantVoiceExperienceVersion, published["published_version_id"]
            )
            version.context_schema_id = "missing-schema"
            db.commit()
        self.assertEqual(self._get(published["slug"]).status_code, 404)
