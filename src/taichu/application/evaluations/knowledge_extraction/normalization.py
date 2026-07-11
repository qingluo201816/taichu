"""Stable normalization helpers used by deterministic evaluation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


_WHITESPACE_PATTERN = re.compile(r"\s+")
_COMMON_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "：": ":",
        "；": ";",
        "！": "!",
        "？": "?",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "《": "<",
        "》": ">",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
)


def normalize_identity(value: str) -> str:
    """Normalize a card name/alias without deleting identity-bearing content."""

    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(_COMMON_PUNCTUATION_TRANSLATION)
    normalized = _WHITESPACE_PATTERN.sub("", normalized)
    return normalized.casefold()


def normalize_exact_value(value: Any) -> Any:
    """Normalize exact-comparison values while treating missing/null as empty."""

    if value is None:
        return ""
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).strip()
        return normalized.translate(_COMMON_PUNCTUATION_TRANSLATION)
    if isinstance(value, list):
        return [normalize_exact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_exact_value(item) for key, item in sorted(value.items())}
    return value


def normalize_set(values: Any) -> frozenset[Any]:
    """Normalize one JSON array into a deterministic comparison set."""

    if values is None:
        return frozenset()
    if not isinstance(values, (list, tuple, set, frozenset)):
        values = [values]
    normalized: set[Any] = set()
    for value in values:
        if isinstance(value, str):
            normalized.add(normalize_identity(value))
        else:
            exact = normalize_exact_value(value)
            if isinstance(exact, (list, dict)):
                exact = repr(exact)
            normalized.add(exact)
    normalized.discard("")
    return frozenset(normalized)


def normalized_identities(name: str, aliases: Iterable[str]) -> frozenset[str]:
    """Return all non-empty normalized identity strings for one card."""

    values = {normalize_identity(name)}
    values.update(normalize_identity(alias) for alias in aliases)
    values.discard("")
    return frozenset(values)
