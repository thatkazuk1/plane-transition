"""Pure text parsing: extract Plane work-item references. No network calls."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

IDENTIFIER_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
    "complete",
    "completes",
    "completed",
)

# How far past a closing keyword to look for identifiers, in characters.
KEYWORD_WINDOW = 120


def parse(
    text: str,
    keywords: Sequence[str] = DEFAULT_KEYWORDS,
    require_keyword: bool = True,
    prefixes: Iterable[str] | None = None,
) -> list[tuple[str, int]]:
    """Extract ordered, de-duplicated (PREFIX, sequence) work-item references.

    When require_keyword is True, only identifiers found within
    KEYWORD_WINDOW characters after a closing keyword are considered
    (handles "Closes FOO-1, FOO-2 and FOO-3"). Otherwise every identifier
    in the text is a candidate. If prefixes is given, results are filtered
    to those prefixes (case-insensitive).
    """
    if require_keyword:
        tokens = _tokens_after_keywords(text, keywords)
    else:
        tokens = [m.group(0) for m in IDENTIFIER_RE.finditer(text)]

    prefix_set = {p.upper() for p in prefixes} if prefixes else None

    seen: set[tuple[str, int]] = set()
    ordered: list[tuple[str, int]] = []
    for token in tokens:
        prefix, _, seq = token.rpartition("-")
        if prefix_set is not None and prefix.upper() not in prefix_set:
            continue
        pair = (prefix.upper(), int(seq))
        if pair in seen:
            continue
        seen.add(pair)
        ordered.append(pair)
    return ordered


def _tokens_after_keywords(text: str, keywords: Sequence[str]) -> list[str]:
    if not keywords:
        return []
    keyword_pattern = "|".join(re.escape(k) for k in keywords)
    keyword_re = re.compile(rf"\b(?:{keyword_pattern})\b", re.IGNORECASE)

    tokens: list[str] = []
    for kw_match in keyword_re.finditer(text):
        window = text[kw_match.end() : kw_match.end() + KEYWORD_WINDOW]
        tokens.extend(m.group(0) for m in IDENTIFIER_RE.finditer(window))
    return tokens
