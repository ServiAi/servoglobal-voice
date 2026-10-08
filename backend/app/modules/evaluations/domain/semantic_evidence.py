from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.modules.agents.public import AgentEvaluationSnapshot
from app.modules.voice.public import (
    TranscriptCompleteness,
    VoiceConversationEvidence,
    VoiceToolOutcome,
)

EVIDENCE_VERSION = "semantic-evidence-v1"
REDACTION_VERSION = "transcript-redaction-v1"

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_BEARER = re.compile(r"(?i)\b(?:authorization\s*[:=]?\s*)?bearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|webhook[_ -]?secret)\s*[:=]\s*[^\s,;]+"
)
_DOCUMENT = re.compile(
    r"(?i)\b(?:c[eé]dula|documento|identificaci[oó]n|dni|pasaporte)\s*(?:n[uú]mero\s*)?(?:[:#-]\s*)?[\d][\d. -]{3,}[\d]"
)
_ACCOUNT = re.compile(
    r"(?i)\b(?:cuenta(?:\s+bancaria)?|tarjeta(?:\s+de\s+cr[eé]dito)?)\s*(?:n[uú]mero\s*)?(?:[:#-]\s*)?[\d][\d -]{4,}[\d]"
)
# Phones are matched by shape, never by digit count alone, so budgets, amounts,
# ticket ids and numeric dates survive: international "+CC ..." numbers, 3-3-4
# separated groups, and bare Colombian mobiles (3XXXXXXXXX, optional 57 prefix;
# same 10-digit rule as crm normalize_phone).
_PHONE = re.compile(
    r"(?<![\w.,$])(?:"
    r"\+\d{1,3}[\s().-]*\d(?:[\s().-]*\d){6,11}"
    r"|\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"
    r"|(?:57)?3\d{9}"
    r")(?![\w]|[.,]\d)"
)


def redact_text(value: str) -> str:
    """Redact known structured identifiers (transcript-redaction-v1).

    Not general DLP: names, addresses and other contextual PII are NOT inferred;
    that is deferred to provider qualification/privacy.
    """
    value = _SECRET.sub("[REDACTED_SECRET]", value)
    value = _BEARER.sub("[REDACTED_TOKEN]", value)
    value = _DOCUMENT.sub("[REDACTED_DOCUMENT]", value)
    value = _ACCOUNT.sub("[REDACTED_ACCOUNT]", value)
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    return _PHONE.sub("[REDACTED_PHONE]", value)


@dataclass(frozen=True)
class SemanticTranscriptTurn:
    event_id: str
    sequence: int | None
    speaker: str
    text: str
    occurred_at: datetime


@dataclass(frozen=True)
class SemanticEvaluationEvidenceV1:
    evidence_version: str
    tenant_id: str
    session_id: str
    purpose: str
    terminal_status: str
    ended_at: datetime | None
    agent_version_id: str
    agent_snapshot: AgentEvaluationSnapshot
    transcript_completeness: TranscriptCompleteness
    redaction_version: str
    turns: tuple[SemanticTranscriptTurn, ...]
    tool_outcomes: tuple[VoiceToolOutcome, ...]
    source_event_ids: tuple[str, ...]
    evidence_hash: str


class SemanticEvidenceUnavailableError(ValueError):
    code = "semantic_evidence_unavailable"


def build_semantic_evidence(
    conversation: VoiceConversationEvidence,
    agent_snapshot: AgentEvaluationSnapshot,
) -> SemanticEvaluationEvidenceV1:
    if conversation.transcript_completeness != TranscriptCompleteness.COMPLETE:
        raise SemanticEvidenceUnavailableError("transcript_evidence_incomplete")
    if (
        not conversation.agent_version_id
        or agent_snapshot.agent_version_id != conversation.agent_version_id
        or agent_snapshot.tenant_id != conversation.tenant_id
    ):
        raise SemanticEvidenceUnavailableError("historical_evidence_missing")
    if agent_snapshot.agent_id == "" or agent_snapshot.agent_version_id == "":
        raise SemanticEvidenceUnavailableError("historical_evidence_missing")
    if any(not turn.event_id or turn.speaker not in {"user", "assistant"} for turn in conversation.turns):
        raise SemanticEvidenceUnavailableError("transcript_turn_invalid")

    safe_agent = replace(
        agent_snapshot,
        name=redact_text(agent_snapshot.name),
        description=redact_text(agent_snapshot.description) if agent_snapshot.description else None,
        role=redact_text(agent_snapshot.role),
        objective=redact_text(agent_snapshot.objective),
        system_prompt=redact_text(agent_snapshot.system_prompt),
        greeting=redact_text(agent_snapshot.greeting),
        closing=redact_text(agent_snapshot.closing),
    )
    turns = tuple(
        SemanticTranscriptTurn(
            event_id=turn.event_id,
            sequence=turn.sequence,
            speaker=turn.speaker,
            text=redact_text(turn.text),
            occurred_at=_utc(turn.occurred_at),
        )
        for turn in conversation.turns
    )
    ended_at = _utc(conversation.ended_at) if conversation.ended_at else None
    evidence = SemanticEvaluationEvidenceV1(
        evidence_version=EVIDENCE_VERSION,
        tenant_id=conversation.tenant_id,
        session_id=conversation.session_id,
        purpose=conversation.purpose,
        terminal_status=conversation.terminal_status,
        ended_at=ended_at,
        agent_version_id=safe_agent.agent_version_id,
        agent_snapshot=safe_agent,
        transcript_completeness=conversation.transcript_completeness,
        redaction_version=REDACTION_VERSION,
        turns=turns,
        tool_outcomes=conversation.tool_outcomes,
        source_event_ids=tuple(
            [turn.event_id for turn in turns] + [outcome.event_id for outcome in conversation.tool_outcomes]
        ),
        evidence_hash="",
    )
    return replace(evidence, evidence_hash=_hash_payload(evidence_payload(evidence)))


def evidence_payload(evidence: SemanticEvaluationEvidenceV1) -> dict:
    """The exact canonical (redacted) document that evidence_hash covers; also what a run stores."""
    return {
        "evidence_version": evidence.evidence_version,
        "tenant_id": evidence.tenant_id,
        "session_id": evidence.session_id,
        "purpose": evidence.purpose,
        "terminal_status": evidence.terminal_status,
        "ended_at": evidence.ended_at.isoformat() if evidence.ended_at else None,
        "agent_version_id": evidence.agent_version_id,
        "agent_snapshot": _agent_dict(evidence.agent_snapshot),
        "transcript_completeness": evidence.transcript_completeness.value,
        "redaction_version": evidence.redaction_version,
        "turns": [
            {
                "event_id": turn.event_id,
                "sequence": turn.sequence,
                "speaker": turn.speaker,
                "text": turn.text,
                "occurred_at": turn.occurred_at.isoformat(),
            }
            for turn in evidence.turns
        ],
        "tool_outcomes": [
            {
                "event_id": outcome.event_id,
                "tool_key": outcome.tool_key,
                "status": outcome.status,
                "duration_ms": outcome.duration_ms,
                "error_code": outcome.error_code,
            }
            for outcome in evidence.tool_outcomes
        ],
    }


def evidence_from_payload(payload: dict, *, expected_hash: str) -> SemanticEvaluationEvidenceV1:
    """Rebuild stored evidence and verify its integrity; any drift fails closed."""
    try:
        if _hash_payload(payload) != expected_hash or payload["evidence_version"] != EVIDENCE_VERSION:
            raise SemanticEvidenceUnavailableError("semantic_evidence_integrity_failed")
        agent = AgentEvaluationSnapshot(
            **{**payload["agent_snapshot"], "enabled_tool_keys": tuple(payload["agent_snapshot"]["enabled_tool_keys"])}
        )
        ended_at = payload["ended_at"]
        return SemanticEvaluationEvidenceV1(
            evidence_version=payload["evidence_version"],
            tenant_id=payload["tenant_id"],
            session_id=payload["session_id"],
            purpose=payload["purpose"],
            terminal_status=payload["terminal_status"],
            ended_at=datetime.fromisoformat(ended_at) if ended_at else None,
            agent_version_id=payload["agent_version_id"],
            agent_snapshot=agent,
            transcript_completeness=TranscriptCompleteness(payload["transcript_completeness"]),
            redaction_version=payload["redaction_version"],
            turns=tuple(
                SemanticTranscriptTurn(
                    event_id=row["event_id"], sequence=row["sequence"], speaker=row["speaker"],
                    text=row["text"], occurred_at=datetime.fromisoformat(row["occurred_at"]),
                )
                for row in payload["turns"]
            ),
            tool_outcomes=tuple(VoiceToolOutcome(**row) for row in payload["tool_outcomes"]),
            source_event_ids=tuple(
                [row["event_id"] for row in payload["turns"]] + [row["event_id"] for row in payload["tool_outcomes"]]
            ),
            evidence_hash=expected_hash,
        )
    except SemanticEvidenceUnavailableError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticEvidenceUnavailableError("semantic_evidence_integrity_failed") from exc


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _agent_dict(snapshot: AgentEvaluationSnapshot) -> dict:
    return {
        "tenant_id": snapshot.tenant_id,
        "agent_version_id": snapshot.agent_version_id,
        "agent_id": snapshot.agent_id,
        "version": snapshot.version,
        "language": snapshot.language,
        "name": snapshot.name,
        "description": snapshot.description,
        "role": snapshot.role,
        "objective": snapshot.objective,
        "system_prompt": snapshot.system_prompt,
        "greeting": snapshot.greeting,
        "closing": snapshot.closing,
        "response_style": snapshot.response_style,
        "interruptions": snapshot.interruptions,
        "turn_detection": snapshot.turn_detection,
        "confirmation_strategy": snapshot.confirmation_strategy,
        "agent_first": snapshot.agent_first,
        "enabled_tool_keys": list(snapshot.enabled_tool_keys),
    }


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
