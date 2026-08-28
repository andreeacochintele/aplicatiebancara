"""Deterministic name -> beneficiary matching. Pure functions, no DB, no LLM
— unit-testable on plain data.

The agent only ever sends money to someone the user has already saved as a
beneficiary. "Trimite 100 lei lui Alex" is resolved by matching "Alex"
against the user's own `beneficiaries` list here; the LLM never supplies a
phone number or IBAN.
"""
import unicodedata

from app.payments.models import Beneficiary

_ROMANIAN_FOLD = str.maketrans({"ș": "s", "ş": "s", "ț": "t", "ţ": "t", "ă": "a", "â": "a", "î": "i"})


def normalize(value: str) -> str:
    """lowercase, strip diacritics, collapse whitespace."""
    lowered = value.strip().lower().translate(_ROMANIAN_FOLD)
    stripped = "".join(c for c in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(c))
    return " ".join(stripped.split())


def match_beneficiaries(query: str, beneficiaries: list[Beneficiary]) -> list[Beneficiary]:
    """Candidates whose name matches `query`.

    Exact normalized full-name match wins outright (returns only those).
    Otherwise: every token of the query must be a prefix of some token of
    the name — so "alex" matches "Alex Pop" and "Alex Ionescu", "alex pop"
    matches only "Alex Pop". The caller decides what 0 / 1 / many means
    (ask, proceed, disambiguate) — this never guesses when it's ambiguous.
    """
    q = normalize(query)
    if not q:
        return []

    exact = [b for b in beneficiaries if normalize(b.name) == q]
    if exact:
        return exact

    q_tokens = q.split()
    matches: list[Beneficiary] = []
    for beneficiary in beneficiaries:
        name_tokens = normalize(beneficiary.name).split()
        if all(any(nt.startswith(qt) for nt in name_tokens) for qt in q_tokens):
            matches.append(beneficiary)
    return matches
