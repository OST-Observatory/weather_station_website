"""CSV formula-injection hardening for spreadsheet clients."""

from __future__ import annotations

import re

# Leading whitespace then a formula trigger, including common fullwidth variants.
_FORMULA_PREFIX = re.compile(
    r'^[\s\t\r\n]*'
    r'([=\+\-@\t\r\n]|'
    r'\uff1d|'  # fullwidth =
    r'\uff0b|'  # fullwidth +
    r'\uff0d|'  # fullwidth -
    r'\uff20)'  # fullwidth @
)


def sanitize_csv_cell(value) -> str:
    """
    Neutralize spreadsheet formula injection while preserving display text.

    Returns a string safe to pass to csv.writer (which applies RFC-4180 quoting).
    """
    if value is None:
        return ''
    text = value if isinstance(value, str) else str(value)
    if not text:
        return ''
    if _FORMULA_PREFIX.match(text):
        # Force text interpretation in Excel/LibreOffice/Google Sheets.
        return "'" + text
    return text
