from app.ai.locale import DEFAULT_LOCALE, get_locale


def test_get_locale_accepts_supported_values():
    assert get_locale("ro") == "ro"
    assert get_locale("en") == "en"


def test_get_locale_falls_back_to_default_when_missing_or_unsupported():
    assert get_locale(None) == DEFAULT_LOCALE
    assert get_locale("fr") == DEFAULT_LOCALE
    assert get_locale("") == DEFAULT_LOCALE
