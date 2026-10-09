from sqlalchemy import select

from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextSchema
from app.modules.voice_experiences.domain.views import (
    VoiceContextFieldSnapshot,
    VoiceContextOptionSnapshot,
    VoiceContextSchemaSnapshot,
)


class SqlAlchemyVoiceContextSchemaReader:
    def __init__(self, session: object) -> None:
        self.session = session

    def get_schema_snapshot(
        self, tenant_id: str, schema_id: str
    ) -> VoiceContextSchemaSnapshot | None:
        schema = self.session.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
        )
        if schema is None:
            return None
        return VoiceContextSchemaSnapshot(
            id=schema.id,
            schema_key=schema.schema_key,
            version=schema.version,
            name=schema.name,
            description=schema.description,
            fields=tuple(
                VoiceContextFieldSnapshot(
                    key=field.key,
                    label=field.label,
                    description=field.description,
                    field_type=field.field_type,
                    collection_mode=field.collection_mode,
                    required=field.required,
                    position=field.position,
                    options=tuple(
                        VoiceContextOptionSnapshot(
                            value=str(option["value"]), label=str(option["label"])
                        )
                        for option in (field.options_json or ())
                    ),
                )
                for field in schema.fields
            ),
        )
