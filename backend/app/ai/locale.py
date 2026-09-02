"""Shared request-locale dependency for every AI-facing router.

The site's language preference (LanguageToggle, stored client-side in
localStorage — see frontend/src/i18n/config.ts) is sent on every API request
as the X-Locale header (frontend/src/api/apiClient.ts), rather than as a
field on each individual request schema: every agent-facing endpoint needs
the same value, and a header keeps it out of OrchestratorChatRequest/
AIInsightPublic/etc. entirely, so this is additive with zero shared-contract
changes for the other three routers that don't care about it.

Before this, every agent guessed the reply language from the user's message
text (each system prompt: "respond in the same language... default to
Romanian if ambiguous"). That guess is no longer needed for a routed
request — the site itself already knows which language the user picked.
"""
from fastapi import Header

SUPPORTED_LOCALES = ("ro", "en")
DEFAULT_LOCALE = "ro"  # matches the app's existing ambiguous-message default


def get_locale(x_locale: str | None = Header(default=None, alias="X-Locale")) -> str:
    if x_locale in SUPPORTED_LOCALES:
        return x_locale
    return DEFAULT_LOCALE
