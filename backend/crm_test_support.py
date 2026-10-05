"""Test helper: drive CRM call ingestion from an Analytics ``Call`` row, the way
the Voice Legacy ingestion adapter does (row -> ``CallRef`` -> CRM)."""

from app.modules.crm.application.call_ingestion_service import CrmIngestionService as _CrmIngestionService
from app.services.legacy_call_payload_adapter import call_ref_from_call


class CrmIngestionService:
    def __init__(self, db) -> None:
        self._service = _CrmIngestionService(db)

    def process_ultravox_event(self, payload, call) -> None:
        self._service.process_call_event(payload, call_ref_from_call(call))
