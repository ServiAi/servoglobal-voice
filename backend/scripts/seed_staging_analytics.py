from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.identity import Tenant


SEED_PROVIDER = "sprint4a_seed"
TENANT_SLUG = settings.BOOTSTRAP_TENANT_SLUG or "serviglobal-ia"


@dataclass(frozen=True)
class AgentSeed:
    external_agent_id: str
    name: str
    channel_type: str


@dataclass(frozen=True)
class CallSeed:
    external_call_id: str
    agent_external_id: str | None
    day: int
    hour: int
    minute: int
    normalized_status: str
    provider_status: str
    duration_seconds: int | None
    billed_minutes: Decimal | None
    direction: str
    customer_phone: str
    summary: str | None
    short_summary: str | None


AGENTS = (
    AgentSeed("s4a-agent-ventas-1", "Agente Ventas IA", "voice"),
    AgentSeed("s4a-agent-agendamiento-1", "Agente Agendamiento IA", "voice"),
    AgentSeed("s4a-agent-soporte-1", "Agente Soporte IA", "voice"),
)


CALLS = (
    CallSeed("s4a-call-001", "s4a-agent-ventas-1", 1, 8, 15, "answered", "ended", 245, Decimal("5.00"), "outbound", "+573001110001", "Cliente interesado en demo comercial y seguimiento por WhatsApp.", "Demo comercial solicitada."),
    CallSeed("s4a-call-002", "s4a-agent-agendamiento-1", 1, 9, 40, "unanswered", "no_answer", 0, Decimal("0.00"), "outbound", "+573001110002", None, "Sin respuesta."),
    CallSeed("s4a-call-003", "s4a-agent-soporte-1", 1, 11, 5, "answered", "completed", 380, Decimal("7.00"), "inbound", "+573001110003", "Cliente resolvio dudas sobre integracion con CRM.", "Dudas de CRM resueltas."),
    CallSeed("s4a-call-004", None, 1, 13, 25, "failed", "failed", 0, Decimal("0.00"), "outbound", "+573001110004", "Fallo tecnico antes de conectar la llamada.", "Fallo tecnico."),
    CallSeed("s4a-call-005", "s4a-agent-ventas-1", 1, 16, 50, "answered", "ended", 155, Decimal("3.00"), "outbound", "+573001110005", "Cliente pidio cotizacion para automatizacion de ventas.", "Cotizacion solicitada."),
    CallSeed("s4a-call-006", None, 1, 18, 20, "in_progress", "in_progress", None, None, "outbound", "+573001110006", None, "Llamada en curso."),
    CallSeed("s4a-call-007", "s4a-agent-agendamiento-1", 2, 8, 5, "answered", "completed", 510, Decimal("9.00"), "outbound", "+573001110007", "Agenda confirmada para reunion de diagnostico.", "Reunion agendada."),
    CallSeed("s4a-call-008", "s4a-agent-ventas-1", 2, 10, 35, "unanswered", "busy", 0, Decimal("0.00"), "outbound", "+573001110008", None, "Linea ocupada."),
    CallSeed("s4a-call-009", "s4a-agent-soporte-1", 2, 12, 10, "failed", "provider_error", 0, Decimal("0.00"), "outbound", "+573001110009", "Proveedor rechazo el intento por error temporal.", "Error de proveedor."),
    CallSeed("s4a-call-010", None, 2, 14, 45, "answered", "ended", 295, Decimal("5.00"), "inbound", "+573001110010", "Consulta general atendida sin agente asignado.", "Consulta atendida."),
    CallSeed("s4a-call-011", "s4a-agent-agendamiento-1", 2, 17, 15, "unanswered", "no_answer", 0, Decimal("0.00"), "outbound", "+573001110011", None, "Sin respuesta."),
    CallSeed("s4a-call-012", "s4a-agent-soporte-1", 2, 19, 0, "in_progress", "active", None, None, "inbound", "+573001110012", None, "Atencion activa."),
    CallSeed("s4a-call-013", "s4a-agent-ventas-1", 3, 7, 55, "answered", "completed", 610, Decimal("11.00"), "outbound", "+573001110013", "Lead calificado para propuesta enterprise.", "Lead enterprise calificado."),
    CallSeed("s4a-call-014", None, 3, 9, 30, "unanswered", "no_answer", 0, Decimal("0.00"), "outbound", "+573001110014", None, "Sin respuesta."),
    CallSeed("s4a-call-015", "s4a-agent-agendamiento-1", 3, 10, 50, "answered", "ended", 205, Decimal("4.00"), "outbound", "+573001110015", "Reprogramacion de reunion por disponibilidad del cliente.", "Reunion reprogramada."),
    CallSeed("s4a-call-016", "s4a-agent-soporte-1", 3, 12, 20, "failed", "failed", 0, Decimal("0.00"), "outbound", "+573001110016", "Fallo antes del saludo inicial.", "Fallo inicial."),
    CallSeed("s4a-call-017", "s4a-agent-ventas-1", 3, 15, 5, "answered", "completed", 430, Decimal("8.00"), "outbound", "+573001110017", "Cliente acepto recibir propuesta y casos de uso.", "Propuesta requerida."),
    CallSeed("s4a-call-018", None, 3, 18, 40, "in_progress", "in_progress", None, None, "outbound", "+573001110018", None, "Llamada en curso."),
    CallSeed("s4a-call-019", "s4a-agent-agendamiento-1", 4, 8, 25, "answered", "ended", 180, Decimal("3.00"), "outbound", "+573001110019", "Agenda confirmada para seguimiento comercial.", "Seguimiento agendado."),
    CallSeed("s4a-call-020", "s4a-agent-soporte-1", 4, 9, 15, "unanswered", "busy", 0, Decimal("0.00"), "outbound", "+573001110020", None, "Linea ocupada."),
    CallSeed("s4a-call-021", "s4a-agent-ventas-1", 4, 10, 30, "answered", "completed", 720, Decimal("12.00"), "inbound", "+573001110021", "Conversacion larga sobre alcance, precios y tiempos.", "Alcance comercial revisado."),
    CallSeed("s4a-call-022", None, 4, 11, 55, "failed", "provider_error", 0, Decimal("0.00"), "outbound", "+573001110022", "Error temporal del proveedor de voz.", "Error temporal."),
    CallSeed("s4a-call-023", "s4a-agent-agendamiento-1", 4, 13, 10, "answered", "ended", 265, Decimal("5.00"), "outbound", "+573001110023", "Cliente confirmo datos para reunion tecnica.", "Datos confirmados."),
    CallSeed("s4a-call-024", "s4a-agent-soporte-1", 4, 14, 35, "unanswered", "no_answer", 0, Decimal("0.00"), "outbound", "+573001110024", None, "Sin respuesta."),
    CallSeed("s4a-call-025", "s4a-agent-ventas-1", 4, 15, 45, "failed", "failed", 0, Decimal("0.00"), "outbound", "+573001110025", "Fallo de conexion con destino.", "Fallo de conexion."),
    CallSeed("s4a-call-026", None, 4, 16, 20, "answered", "completed", 335, Decimal("6.00"), "inbound", "+573001110026", "Cliente nuevo pidio informacion general del servicio.", "Informacion general."),
    CallSeed("s4a-call-027", "s4a-agent-agendamiento-1", 4, 17, 30, "unanswered", "no_answer", 0, Decimal("0.00"), "outbound", "+573001110027", None, "Sin respuesta."),
    CallSeed("s4a-call-028", "s4a-agent-soporte-1", 4, 18, 5, "in_progress", "active", None, None, "inbound", "+573001110028", None, "Atencion activa."),
)


def ensure_staging_database(db: Session) -> str:
    database_name = db.execute(text("select current_database()")).scalar_one()
    if "staging" not in database_name.lower():
        raise RuntimeError(
            f"Refusing to seed analytics data outside staging database: {database_name}"
        )
    return database_name


def get_tenant(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
    if tenant is None:
        raise RuntimeError(f"Tenant with slug '{TENANT_SLUG}' was not found")
    if tenant.status != "active":
        raise RuntimeError(f"Tenant '{TENANT_SLUG}' is not active")
    return tenant


def upsert_agent(db: Session, tenant_id: str, seed: AgentSeed) -> Agent:
    agent = db.scalar(
        select(Agent).where(
            and_(
                Agent.tenant_id == tenant_id,
                Agent.external_provider == SEED_PROVIDER,
                Agent.external_agent_id == seed.external_agent_id,
            )
        )
    )
    if agent is None:
        agent = Agent(
            tenant_id=tenant_id,
            external_provider=SEED_PROVIDER,
            external_agent_id=seed.external_agent_id,
            name=seed.name,
            channel_type=seed.channel_type,
            status="active",
        )
        db.add(agent)
    else:
        agent.name = seed.name
        agent.channel_type = seed.channel_type
        agent.status = "active"
    return agent


def call_started_at(seed: CallSeed) -> datetime:
    return datetime(2026, 5, seed.day, seed.hour, seed.minute, tzinfo=UTC)


def upsert_call(
    db: Session,
    tenant_id: str,
    agents_by_external_id: dict[str, Agent],
    seed: CallSeed,
) -> Call:
    started_at = call_started_at(seed)
    joined_at = started_at + timedelta(seconds=25) if seed.normalized_status in {"answered", "in_progress"} else None
    ended_at = None
    if seed.normalized_status == "answered" and seed.duration_seconds is not None:
        ended_at = started_at + timedelta(seconds=25 + seed.duration_seconds)
    elif seed.normalized_status == "unanswered":
        ended_at = started_at + timedelta(seconds=65)
    elif seed.normalized_status == "failed":
        ended_at = started_at + timedelta(seconds=35)
    agent = agents_by_external_id.get(seed.agent_external_id or "")

    call = db.scalar(
        select(Call).where(
            and_(
                Call.tenant_id == tenant_id,
                Call.external_provider == SEED_PROVIDER,
                Call.external_call_id == seed.external_call_id,
            )
        )
    )
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "external_call_id": seed.external_call_id,
        "external_provider": SEED_PROVIDER,
        "agent_id": agent.id if agent else None,
        "provider_agent_id": seed.agent_external_id,
        "provider_status": seed.provider_status,
        "normalized_status": seed.normalized_status,
        "started_at": started_at,
        "joined_at": joined_at,
        "ended_at": ended_at,
        "duration_seconds": seed.duration_seconds,
        "billed_minutes": seed.billed_minutes,
        "summary": seed.summary,
        "short_summary": seed.short_summary,
        "recording_url": (
            f"https://recordings.example.invalid/staging/{seed.external_call_id}.mp3"
            if seed.normalized_status == "answered"
            else None
        ),
        "direction": seed.direction,
        "customer_phone": seed.customer_phone,
        "last_synced_at": datetime.now(UTC),
    }
    if call is None:
        call = Call(**values)
        db.add(call)
    else:
        for key, value in values.items():
            setattr(call, key, value)
    return call


def event_specs(seed: CallSeed) -> tuple[tuple[str, int], ...]:
    specs: list[tuple[str, int]] = [("call.created", 0), ("call.ringing", 10)]
    if seed.normalized_status == "answered":
        specs.extend((("call.connected", 25), ("call.completed", 25 + (seed.duration_seconds or 0))))
    elif seed.normalized_status == "unanswered":
        specs.append(("call.no_answer", 65))
    elif seed.normalized_status == "failed":
        specs.append(("call.failed", 35))
    elif seed.normalized_status == "in_progress":
        specs.append(("call.connected", 25))
    return tuple(specs)


def upsert_events(db: Session, tenant_id: str, call: Call, seed: CallSeed) -> int:
    inserted_or_updated = 0
    for event_type, offset_seconds in event_specs(seed):
        provider_event_id = f"{seed.external_call_id}:{event_type}"
        received_at = call.started_at + timedelta(seconds=offset_seconds)
        payload_json = {
            "seed": "sprint_4a",
            "provider": SEED_PROVIDER,
            "external_call_id": seed.external_call_id,
            "event_type": event_type,
            "normalized_status": seed.normalized_status,
        }
        event = db.scalar(
            select(CallEvent).where(
                and_(
                    CallEvent.tenant_id == tenant_id,
                    CallEvent.call_id == call.id,
                    CallEvent.provider_event_id == provider_event_id,
                )
            )
        )
        if event is None:
            event = CallEvent(
                tenant_id=tenant_id,
                call_id=call.id,
                event_type=event_type,
                provider_event_id=provider_event_id,
                payload_json=payload_json,
                received_at=received_at,
            )
            db.add(event)
        else:
            event.event_type = event_type
            event.payload_json = payload_json
            event.received_at = received_at
        inserted_or_updated += 1
    return inserted_or_updated


def upsert_metric_snapshots(db: Session, tenant_id: str) -> int:
    rows = db.execute(
        select(
            func.date(Call.started_at).label("snapshot_date"),
            Call.agent_id,
            func.count(Call.id).label("calls_total"),
            func.count(Call.id).filter(Call.normalized_status == "answered").label("calls_answered"),
            func.count(Call.id).filter(Call.normalized_status == "unanswered").label("calls_unanswered"),
            func.coalesce(func.sum(Call.duration_seconds), 0).label("duration_total_seconds"),
            func.coalesce(func.sum(Call.billed_minutes), Decimal("0.00")).label("billed_minutes"),
        )
        .where(and_(Call.tenant_id == tenant_id, Call.external_provider == SEED_PROVIDER))
        .group_by(func.date(Call.started_at), Call.agent_id)
    ).all()

    touched = 0
    for row in rows:
        filters = [
            MetricSnapshotDaily.tenant_id == tenant_id,
            MetricSnapshotDaily.date == row.snapshot_date,
        ]
        if row.agent_id is None:
            filters.append(MetricSnapshotDaily.agent_id.is_(None))
        else:
            filters.append(MetricSnapshotDaily.agent_id == row.agent_id)

        snapshot = db.scalar(select(MetricSnapshotDaily).where(and_(*filters)))
        if snapshot is None:
            snapshot = MetricSnapshotDaily(
                tenant_id=tenant_id,
                date=row.snapshot_date,
                agent_id=row.agent_id,
            )
            db.add(snapshot)

        snapshot.calls_total = int(row.calls_total)
        snapshot.calls_answered = int(row.calls_answered)
        snapshot.calls_unanswered = int(row.calls_unanswered)
        snapshot.duration_total_seconds = int(row.duration_total_seconds or 0)
        snapshot.billed_minutes = Decimal(row.billed_minutes or Decimal("0.00"))
        touched += 1
    return touched


def summarize(db: Session, tenant_id: str) -> dict[str, int]:
    tables = {
        "agents": Agent,
        "calls": Call,
        "call_events": CallEvent,
        "metric_snapshots_daily": MetricSnapshotDaily,
    }
    return {
        name: db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id))
        for name, model in tables.items()
    }


def main() -> None:
    with SessionLocal() as db:
        database_name = ensure_staging_database(db)
        tenant = get_tenant(db)

        agents_by_external_id = {
            seed.external_agent_id: upsert_agent(db, tenant.id, seed)
            for seed in AGENTS
        }
        db.flush()

        calls_by_external_id: dict[str, Call] = {}
        for seed in CALLS:
            call = upsert_call(db, tenant.id, agents_by_external_id, seed)
            calls_by_external_id[seed.external_call_id] = call
        db.flush()

        event_count = 0
        for seed in CALLS:
            event_count += upsert_events(
                db,
                tenant.id,
                calls_by_external_id[seed.external_call_id],
                seed,
            )

        snapshot_count = upsert_metric_snapshots(db, tenant.id)
        db.commit()

        status_counts = dict(
            db.execute(
                select(Call.normalized_status, func.count(Call.id))
                .where(and_(Call.tenant_id == tenant.id, Call.external_provider == SEED_PROVIDER))
                .group_by(Call.normalized_status)
            ).all()
        )
        agent_counts = defaultdict(int)
        for name, total in db.execute(
            select(func.coalesce(Agent.name, "Sin agente asignado"), func.count(Call.id))
            .select_from(Call)
            .outerjoin(Agent, Call.agent_id == Agent.id)
            .where(and_(Call.tenant_id == tenant.id, Call.external_provider == SEED_PROVIDER))
            .group_by(func.coalesce(Agent.name, "Sin agente asignado"))
        ):
            agent_counts[name] = int(total)

        counts = summarize(db, tenant.id)

    print(f"Seed complete in database={database_name} tenant={tenant.name} ({tenant.id})")
    print(f"Agents upserted={len(AGENTS)}")
    print(f"Calls upserted={len(CALLS)}")
    print(f"Call events upserted={event_count}")
    print(f"Metric snapshots upserted={snapshot_count}")
    print(f"Final tenant counts={counts}")
    print(f"Seed status distribution={dict(status_counts)}")
    print(f"Seed agent distribution={dict(agent_counts)}")


if __name__ == "__main__":
    main()
