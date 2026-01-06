"""Simple YAML-based translator."""

from pathlib import Path
from typing import Any

import yaml


class Translator:
    """Multi-language translator using YAML files."""

    def __init__(self, locales_dir: Path | None = None):
        if locales_dir is None:
            locales_dir = Path(__file__).parent / "locales"
        self.locales_dir = locales_dir
        self._translations: dict[str, dict[str, Any]] = {}
        self._default_lang = "ru"
        self._load_all_locales()

    def _load_all_locales(self) -> None:
        """Load all available locale files."""
        if not self.locales_dir.exists():
            return

        for file_path in self.locales_dir.glob("*.yaml"):
            lang = file_path.stem
            with open(file_path, encoding="utf-8") as f:
                self._translations[lang] = yaml.safe_load(f) or {}

    def get(self, key: str, lang: str | None = None, **kwargs: Any) -> str:
        """
        Get translated string by key.

        Args:
            key: Dot-separated key (e.g., "server.started")
            lang: Language code ("ru", "en")
            **kwargs: Format arguments

        Returns:
            Translated and formatted string
        """
        lang = lang or self._default_lang
        translations = self._translations.get(lang, {})

        # Navigate nested keys
        value = translations
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

        # Fallback to default language
        if value is None and lang != self._default_lang:
            return self.get(key, self._default_lang, **kwargs)

        # Fallback to key itself
        if value is None:
            return key

        # Format with arguments
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except KeyError:
                return value

        return str(value)

    def set_default_language(self, lang: str) -> None:
        """Set default language."""
        self._default_lang = lang

    @property
    def available_languages(self) -> list[str]:
        """Get list of available languages."""
        return list(self._translations.keys())


# Global translator instance
_translator: Translator | None = None


def get_translator() -> Translator:
    """Get or create global translator instance."""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Shortcut for getting translations."""
    return get_translator().get(key, lang, **kwargs)
