from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import unicodedata


@dataclass(frozen=True)
class ClassificationResult:
    stage_key: str | None
    next_action: str | None = None
    reason: str | None = None
    confidence: str = "deterministic_keyword"


class CrmClassifierService:
    NOT_INTERESTED_KEYWORDS = [
        "no estoy interesado",
        "no interes",
        "no esta interesado",
        "no me interesa",
        "no nos interesa",
        "no le interesa",
        "no quiero",
        "no quiere",
        "no queremos",
        "no desea",
        "no deseo",
        "no deseamos",
        "no necesito",
        "no necesitamos",
        "no lo necesito",
        "no aplica",
        "no gracias",
        "por ahora no",
        "no volver a llamar",
        "no contactar",
        "rechaza la oferta",
        "rechazo la oferta",
        "rechaza el servicio",
        "no autoriza",
        "no acepta",
        "not interested",
    ]
    QUALIFIED_KEYWORDS = [
        "interesado",
        "interesa",
        "quiero informacion",
        "quiere informacion",
        "quiero cotizar",
        "quiere cotizar",
        "cotizacion",
        "cotizar",
        "enviar propuesta",
        "propuesta",
        "quiero una demo",
        "quiere una demo",
        "demo",
        "quiero conocer precios",
        "precios",
        "necesito automatizar",
        "automatizar",
        "me sirve",
        "lo podemos revisar",
        "podemos revisar",
        "qualif",
        "price",
    ]
    BOOKING_INTENT_KEYWORDS = [
        "agendar",
        "agenda",
        "cita",
        "reunion",
        "programar",
        "calendar",
        "schedule",
        "appointment",
        "book",
    ]
    FOLLOW_UP_STATUSES = {"voicemail", "unanswered", "failed", "rejected", "cancelled"}

    def classify_lead_stage(
        self,
        call_status: str | None,
        summary: str | None,
        short_summary: str | None,
    ) -> str | None:
        result = self.classify_after_call(call_status, summary, short_summary, None)
        if result.stage_key == "follow_up" and not self._text(summary, short_summary):
            return "follow_up" if (call_status or "").lower() in self.FOLLOW_UP_STATUSES else None
        if result.stage_key == "follow_up" and result.reason == "no_clear_signal":
            return None
        if result.next_action == "confirm_booking" and not self.is_qualified(summary, short_summary, None):
            return None
        return result.stage_key

    def is_not_interested(
        self,
        summary: str | None,
        short_summary: str | None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        text = self._text(summary, short_summary, payload)
        return any(keyword in text for keyword in self.NOT_INTERESTED_KEYWORDS)

    def is_qualified(
        self,
        summary: str | None,
        short_summary: str | None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        text = self._text(summary, short_summary, payload)
        return any(keyword in text for keyword in self.QUALIFIED_KEYWORDS)

    def has_booking_intent(
        self,
        summary: str | None,
        short_summary: str | None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        text = self._text(summary, short_summary, payload)
        return any(keyword in text for keyword in self.BOOKING_INTENT_KEYWORDS)

    def classify_after_call(
        self,
        call_status: str | None,
        summary: str | None,
        short_summary: str | None,
        payload: dict[str, Any] | None = None,
    ) -> ClassificationResult:
        status = (call_status or "").strip().lower()

        if self.is_not_interested(summary, short_summary, payload):
            return ClassificationResult(
                stage_key="not_interested",
                reason="explicit_rejection",
            )

        if self.is_qualified(summary, short_summary, payload):
            return ClassificationResult(
                stage_key="qualified",
                next_action="send_proposal",
                reason="clear_interest",
            )

        if self.has_booking_intent(summary, short_summary, payload):
            return ClassificationResult(
                stage_key="qualified",
                next_action="confirm_booking",
                reason="booking_intent_without_verified_event",
            )

        if status in self.FOLLOW_UP_STATUSES:
            return ClassificationResult(
                stage_key="follow_up",
                reason=status or "call_not_completed",
            )

        return ClassificationResult(
            stage_key="follow_up",
            reason="no_clear_signal",
        )

    def _text(self, summary: str | None, short_summary: str | None, payload: dict[str, Any] | None = None) -> str:
        parts = [summary or "", short_summary or ""]
        if payload:
            parts.extend(self._walk_text(payload))
        text = " ".join(part for part in parts if part)
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()

    def _walk_text(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            texts: list[str] = []
            for nested in value.values():
                texts.extend(self._walk_text(nested))
            return texts
        if isinstance(value, list):
            texts = []
            for nested in value:
                texts.extend(self._walk_text(nested))
            return texts
        return []
