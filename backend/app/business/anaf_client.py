"""ANAF PlatitorTvaRest v9 client - looks up basic company details by CUI
(Romanian fiscal/registration code) from the public, keyless government
registry: https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva

This is a pure external lookup used to pre-fill BusinessProfile fields; it
never writes to the database and the caller (business/router.py) always
lets the user review/edit the result before saving, same as the AI
extraction flow in ai/bulk_transfer_extraction.py never submits transfers
on its own. No local CUI control-digit checksum is attempted here - the
published algorithm has several conflicting variants online, so ANAF's own
"not found" response is treated as the single source of truth for validity.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

from app.core.exceptions import NotFoundError, ValidationError

_ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def normalize_cui(raw_cui: str) -> str:
    digits = re.sub(r"\D", "", raw_cui.strip().upper().removeprefix("RO"))
    if not (2 <= len(digits) <= 10):
        raise ValidationError("CUI invalid: trebuie sa contina intre 2 si 10 cifre")
    return digits


def lookup_cui(raw_cui: str) -> dict[str, Any]:
    cui = normalize_cui(raw_cui)
    try:
        response = httpx.post(
            _ANAF_URL,
            json=[{"cui": int(cui), "data": date.today().isoformat()}],
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ValidationError("Serviciul ANAF nu a putut fi contactat, introduceti datele manual") from exc

    found = payload.get("found") or []
    if not found:
        raise NotFoundError("CUI-ul nu a fost gasit in registrul ANAF")

    general = found[0].get("date_generale") or {}
    return {
        "cui": str(general.get("cui", cui)),
        "company_name": general.get("denumire") or "",
        "registration_number": general.get("nrRegCom") or None,
        "address": general.get("adresa") or None,
        "is_active": not bool(general.get("stare_inactiv")),
    }
