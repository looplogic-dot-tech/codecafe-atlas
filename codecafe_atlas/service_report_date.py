from __future__ import annotations

import re
import unicodedata
from datetime import date

SPANISH_MONTHS = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

# Common OCR substitutions restricted to date tokens only.
_OCR_DIGIT_TRANSLATION = str.maketrans({
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "|": "1",
    "S": "5",
    "B": "8",
})

_DATE_WITH_SEPARATOR = re.compile(
    r"(?<![0-9A-Z])"
    r"([0-9OQDIL|SB]{1,2})\s*[-./\\]\s*"
    r"([0-9OQDIL|SB]{1,2})\s*[-./\\]\s*"
    r"([0-9OQDIL|SB]{2,4})"
    r"(?![0-9A-Z])",
    re.IGNORECASE,
)

# Some OCR engines replace separators with spaces. This pattern is used only
# inside a label-associated window or a tightly cropped date field.
_DATE_WITH_SPACES = re.compile(
    r"(?<![0-9A-Z])"
    r"([0-9OQDIL|SB]{1,2})\s+"
    r"([0-9OQDIL|SB]{1,2})\s+"
    r"([0-9OQDIL|SB]{4})"
    r"(?![0-9A-Z])",
    re.IGNORECASE,
)

_DATE_YEAR_FIRST = re.compile(
    r"(?<![0-9A-Z])"
    r"([0-9OQDIL|SB]{4})\s*[-./\\]\s*"
    r"([0-9OQDIL|SB]{1,2})\s*[-./\\]\s*"
    r"([0-9OQDIL|SB]{1,2})"
    r"(?![0-9A-Z])",
    re.IGNORECASE,
)

_DATE_COMPACT_MANUAL = re.compile(
    r"^\s*([0-9]{2})([0-9]{2})([0-9]{4})\s*$"
)

_PROVIDER_DATE_LABEL = re.compile(
    r"fecha.{0,24}reporte.{0,56}prestador.{0,36}servicio",
    re.IGNORECASE | re.DOTALL,
)


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.upper()


def _token_to_int(token: str) -> int | None:
    cleaned = token.upper().translate(_OCR_DIGIT_TRANSLATION)
    cleaned = re.sub(r"[^0-9]", "", cleaned)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _validated_iso(day_token: str, month_token: str, year_token: str) -> str:
    day = _token_to_int(day_token)
    month = _token_to_int(month_token)
    year = _token_to_int(year_token)
    if day is None or month is None or year is None:
        return ""
    if year < 100:
        year += 2000
    if not 2000 <= year <= 2099:
        return ""
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _extract_first_date(value: str, allow_space_separators: bool) -> str:
    for match in _DATE_WITH_SEPARATOR.finditer(value):
        parsed = _validated_iso(match.group(1), match.group(2), match.group(3))
        if parsed:
            return parsed

    for match in _DATE_YEAR_FIRST.finditer(value):
        parsed = _validated_iso(match.group(3), match.group(2), match.group(1))
        if parsed:
            return parsed

    if allow_space_separators:
        for match in _DATE_WITH_SPACES.finditer(value):
            parsed = _validated_iso(match.group(1), match.group(2), match.group(3))
            if parsed:
                return parsed
    return ""


def extract_provider_report_date(text: str, *, allow_unlabeled: bool = False) -> tuple[str, int]:
    """Extract the provider's report date and normalize it as YYYY-MM-DD.

    Labeled extraction is preferred so other dates in the service certificate do
    not determine the export month. ``allow_unlabeled`` is intended only for OCR
    text produced from a tightly cropped image of this exact form field.
    """
    normalized = _ascii_text(text)
    if not normalized.strip():
        return "", 0

    for label in _PROVIDER_DATE_LABEL.finditer(normalized):
        start = label.start()
        end = min(len(normalized), label.end() + 180)
        parsed = _extract_first_date(normalized[start:end], allow_space_separators=True)
        if parsed:
            return parsed, 98

    if allow_unlabeled:
        parsed = _extract_first_date(normalized, allow_space_separators=True)
        if parsed:
            return parsed, 86
    return "", 0


def format_manual_report_date_input(value: str) -> str:
    """Format up to eight typed digits as ``DD-MM-YYYY``.

    The helper intentionally ignores separators so typing or pasting
    ``09072026`` becomes ``09-07-2026``. Partial input remains editable.
    """
    digits = re.sub(r"[^0-9]", "", value or "")[:8]
    if len(digits) <= 2:
        return digits
    if len(digits) <= 4:
        return f"{digits[:2]}-{digits[2:]}"
    return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"


def parse_manual_report_date(value: str) -> str:
    """Parse a manually corrected date entered as DD-MM-YYYY, YYYY-MM-DD or DDMMYYYY."""
    normalized = _ascii_text(value)
    parsed = _extract_first_date(normalized, allow_space_separators=False)
    if parsed:
        return parsed
    compact = _DATE_COMPACT_MANUAL.fullmatch(normalized)
    if compact:
        return _validated_iso(compact.group(1), compact.group(2), compact.group(3))
    return ""


def display_report_date(iso_date: str) -> str:
    try:
        parsed = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return ""
    return parsed.strftime("%d-%m-%Y")


def date_folder_names(iso_date: str) -> tuple[str, str]:
    """Return the two date levels used by service-certificate exports.

    Valid dates are organized as ``Año/Mes`` using the Spanish month name
    without a numeric prefix. Unknown dates keep the same two-level
    structure so the category is always the third level.
    """
    try:
        parsed = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return "Año no identificado", "Mes no identificado"
    return f"{parsed.year:04d}", SPANISH_MONTHS[parsed.month]


def year_folder_name(iso_date: str) -> str:
    return date_folder_names(iso_date)[0]


def month_folder_name(iso_date: str) -> str:
    return date_folder_names(iso_date)[1]
