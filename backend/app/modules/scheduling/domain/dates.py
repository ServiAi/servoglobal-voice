from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytz


BOGOTA_TZ = pytz.timezone("America/Bogota")
SPANISH_DAY_NAMES = [
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
]
WEEKDAY_INDEX = {name: index for index, name in enumerate(SPANISH_DAY_NAMES)}
DIRECT_RELATIVE_EXPRESSIONS = {
    "hoy": 0,
    "manana": 1,
    "pasado manana": 2,
}


@dataclass(frozen=True)
class ResolvedTemporalExpression:
    date: str
    day_name: str
    reference_datetime: str
    matched_expression: str
    normalized_expression: str
    strategy: str
    days_ahead: int
    target_weekday: str | None = None

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "day_name": self.day_name,
            "reference_datetime": self.reference_datetime,
            "matched_expression": self.matched_expression,
            "normalized_expression": self.normalized_expression,
            "strategy": self.strategy,
            "days_ahead": self.days_ahead,
            "target_weekday": self.target_weekday,
        }


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_temporal_expression(value: str) -> str:
    cleaned = _strip_accents(value or "").lower().strip()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def parse_reference_datetime(reference_datetime: str | None = None) -> datetime:
    if not reference_datetime:
        return datetime.now(BOGOTA_TZ)

    raw_value = reference_datetime.strip()

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw_value, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(
                f"No se pudo parsear la fecha de referencia: {reference_datetime}"
            )

    if parsed.tzinfo is None:
        return BOGOTA_TZ.localize(parsed)

    return parsed.astimezone(BOGOTA_TZ)


def _build_resolution(
    target_date: date,
    reference_dt: datetime,
    matched_expression: str,
    normalized_expression: str,
    strategy: str,
    days_ahead: int,
    target_weekday: str | None = None,
) -> ResolvedTemporalExpression:
    return ResolvedTemporalExpression(
        date=target_date.isoformat(),
        day_name=SPANISH_DAY_NAMES[target_date.weekday()],
        reference_datetime=reference_dt.strftime("%Y-%m-%d %H:%M:%S"),
        matched_expression=matched_expression,
        normalized_expression=normalized_expression,
        strategy=strategy,
        days_ahead=days_ahead,
        target_weekday=target_weekday,
    )


def resolve_temporal_expression(
    expression: str,
    reference_datetime: str | None = None,
) -> ResolvedTemporalExpression:
    if not expression or not expression.strip():
        raise ValueError("La expresion temporal no puede estar vacia.")

    reference_dt = parse_reference_datetime(reference_datetime)
    reference_date = reference_dt.date()
    normalized_expression = normalize_temporal_expression(expression)

    if normalized_expression in DIRECT_RELATIVE_EXPRESSIONS:
        days_ahead = DIRECT_RELATIVE_EXPRESSIONS[normalized_expression]
        target_date = reference_date + timedelta(days=days_ahead)
        return _build_resolution(
            target_date=target_date,
            reference_dt=reference_dt,
            matched_expression=expression,
            normalized_expression=normalized_expression,
            strategy="relative_keyword",
            days_ahead=days_ahead,
        )

    weekday_pattern = re.compile(
        r"^(?:(el|este|esta|proximo|proxima)\s+)?"
        r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)$"
    )
    weekday_match = weekday_pattern.match(normalized_expression)

    if weekday_match:
        qualifier, weekday_name = weekday_match.groups()
        target_weekday_index = WEEKDAY_INDEX[weekday_name]
        current_weekday_index = reference_date.weekday()
        days_ahead = (target_weekday_index - current_weekday_index) % 7

        if qualifier in {"proximo", "proxima"}:
            if days_ahead == 0:
                days_ahead = 7
            strategy = "next_weekday_strict"
        else:
            strategy = "upcoming_weekday"

        target_date = reference_date + timedelta(days=days_ahead)
        return _build_resolution(
            target_date=target_date,
            reference_dt=reference_dt,
            matched_expression=expression,
            normalized_expression=normalized_expression,
            strategy=strategy,
            days_ahead=days_ahead,
            target_weekday=weekday_name,
        )

    raise ValueError(f"Expresion temporal no soportada: {expression}")


def is_iso_like_date(value: str) -> bool:
    if not value:
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()))
