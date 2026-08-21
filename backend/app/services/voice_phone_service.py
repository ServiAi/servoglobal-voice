from __future__ import annotations

from dataclasses import dataclass

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType


SUPPORTED_OUTBOUND_COUNTRIES = frozenset({"AR", "CL", "CO", "EC", "MX", "PA", "PE", "US"})
FORMAT_ONLY_COUNTRIES = frozenset({"MX", "US"})


class VoicePhoneValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedVoicePhone:
    e164: str
    country: str


def normalize_outbound_phone(
    value: str,
    *,
    default_country: str | None = None,
    allowed_countries: set[str] | frozenset[str] = SUPPORTED_OUTBOUND_COUNTRIES,
) -> NormalizedVoicePhone:
    country_hint = default_country.upper() if default_country else None
    if country_hint and country_hint not in SUPPORTED_OUTBOUND_COUNTRIES:
        raise VoicePhoneValidationError("Unsupported default country.")
    try:
        parsed = phonenumbers.parse(value, country_hint)
    except phonenumbers.NumberParseException as exc:
        raise VoicePhoneValidationError("Invalid phone number.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise VoicePhoneValidationError("Invalid phone number.")
    country = phonenumbers.region_code_for_number(parsed)
    if not country or country not in SUPPORTED_OUTBOUND_COUNTRIES or country not in allowed_countries:
        raise VoicePhoneValidationError("Phone destination is not allowed.")
    number_type = phonenumbers.number_type(parsed)
    is_mobile = number_type == PhoneNumberType.MOBILE or (
        country == "CL"
        and number_type == PhoneNumberType.FIXED_LINE_OR_MOBILE
        and str(parsed.national_number).startswith("9")
    )
    if country not in FORMAT_ONLY_COUNTRIES and not is_mobile:
        raise VoicePhoneValidationError("Phone number must be mobile.")
    return NormalizedVoicePhone(
        e164=phonenumbers.format_number(parsed, PhoneNumberFormat.E164),
        country=country,
    )


def normalize_caller_id(value: str, *, default_country: str | None = None) -> str:
    try:
        parsed = phonenumbers.parse(value, default_country.upper() if default_country else None)
    except phonenumbers.NumberParseException as exc:
        raise VoicePhoneValidationError("Invalid caller ID.") from exc
    country = phonenumbers.region_code_for_number(parsed)
    if not phonenumbers.is_valid_number(parsed) or country not in SUPPORTED_OUTBOUND_COUNTRIES:
        raise VoicePhoneValidationError("Invalid caller ID.")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
