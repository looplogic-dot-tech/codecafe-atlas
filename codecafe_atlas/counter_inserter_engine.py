#!/usr/bin/env python3
"""
CodeCafe Atlas — Insertador flexible de contadores

Objetivo estricto:
- Leer una hoja maestra XLSX u ODS.
- Leer un reporte compatible de CodeCafe Atlas (CSV, XLSX u ODS).
- Relacionar equipos por número de serie.
- Trabajar en la pestaña y filas detectadas o seleccionadas.
- Trabajar exclusivamente con registros cuya LOCALIDAD sea Torreón.
- Escribir exclusivamente en las columnas de contador detectadas o seleccionadas.
- No agregar columnas, hojas ni campos.
- No modificar fórmulas.
- Completar con 0 las celdas destino realmente vacías para cada serie exacta con al menos un contador válido.
- No aceptar coincidencias aproximadas, correcciones OCR ni series parecidas.
- Generar un CSV adicional con toda discrepancia que requiera revisión manual.
- Guardar siempre una copia nueva en el mismo formato que la hoja maestra.

La aplicación usa solamente la biblioteca estándar de Python.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import ipaddress
import json
import os
import posixpath
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

APP_NAME = "CodeCafe Atlas — Insertador inteligente de contadores"
APP_VERSION = "1.0.24.48"

MASTER_SHEET_CANDIDATES = (
    "1__Consumo_de_Impresión_Mono",
    "1. Consumo de Impresión Mono",
)
MASTER_HEADER_SCAN_ROWS = 20
MASTER_FIRST_ROW = 821
MASTER_LAST_ROW = 1404
# La hoja oficial existe en más de una disposición histórica. La columna de
# serie puede ser E o F, por lo que se detecta por encabezado en cada archivo.
MASTER_SERIAL_COL_FALLBACK = 5
MASTER_LOCALITY_COL_FALLBACK = 12
TARGET_FIRST_COL = 37       # AK
TARGET_LAST_COL = 44        # AR
STATUS_VALUE = "En Operación"
TARGET_LOCALITY = "Torreón"
TARGET_MONTH = "Julio"

FIELD_DEFINITIONS = (
    ("principal", "Total de impresiones"),
    ("equivalente", "Total de impresiones equivalentes"),
    ("duplex", "Hojas ambas caras"),
    ("atascos", "Eventos de atasco"),
    ("escaneos", "Total Escaneos"),
    ("copias", "Total de copias"),
    ("color", "Impresiones a color"),
    ("digitalizaciones", "Total Digitalizaciones"),
)

# Cada destino está amarrado a una columna ya existente. No se permite ampliar esto.
TARGETS = (
    ("AK", 37, "(CARTA) Total de impresiones Julio", "principal"),
    ("AL", 38, "(OFICIO) Total de impresiones equivalentes Julio", "equivalente"),
    ("AM", 39, "Hojas ambas caras Julio", "duplex"),
    ("AN", 40, "Eventos de atasco Julio", "atascos"),
    ("AO", 41, "Total Escaneos", "escaneos"),
    ("AP", 42, "Total de copias", "copias"),
    ("AQ", 43, "Impresiones a color", "color"),
    ("AR", 44, "Total Digitalizaciones", "digitalizaciones"),
)
TARGET_BY_KEY = {key: (letter, col, label) for letter, col, label, key in TARGETS}
TARGET_COLS = {col for _, col, _, _ in TARGETS}
AUTHORIZED_WRITE_COLS = set(TARGET_COLS)

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "dc": "http://purl.org/dc/elements/1.1/",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "number": "urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "of": "urn:oasis:names:tc:opendocument:xmlns:of:1.2",
    "calcext": "urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0",
}
for _prefix, _uri in NS.items():
    try:
        ET.register_namespace(_prefix, _uri)
    except ValueError:
        pass

T = "{%s}" % NS["table"]
O = "{%s}" % NS["office"]
X = "{%s}" % NS["text"]


class AtlasError(Exception):
    """Error esperado que puede mostrarse directamente al usuario."""


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().replace("°", "o").replace("º", "o")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_serial(value: Any) -> str:
    text = "" if value is None else str(value).upper().strip()
    return re.sub(r"[^A-Z0-9]", "", text)


def serial_edit_distance(left: str, right: str, limit: int = 2) -> int:
    """Small bounded Damerau-Levenshtein distance for serial typo warnings."""
    left, right = normalize_serial(left), normalize_serial(right)
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous_previous: list[int] | None = None
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, start=1):
        current = [i]
        row_min = i
        for j, char_right in enumerate(right, start=1):
            value = min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (char_left != char_right),
            )
            if (
                previous_previous is not None and i > 1 and j > 1
                and char_left == right[j - 2] and left[i - 2] == char_right
            ):
                value = min(value, previous_previous[j - 2] + 1)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous_previous, previous = previous, current
    return previous[-1]


def similar_master_serials(
    serial_key: str,
    master_records: dict[str, "MasterRecord"],
) -> list[tuple[int, "MasterRecord"]]:
    """Return only close candidates; they are warnings, never automatic matches."""
    if len(serial_key) < 6:
        return []
    candidates: list[tuple[int, MasterRecord]] = []
    for existing_key, record in master_records.items():
        if existing_key == serial_key:
            continue
        distance = serial_edit_distance(serial_key, existing_key, limit=2)
        if distance <= 1:
            candidates.append((distance, record))
    return sorted(candidates, key=lambda item: (item[0], item[1].row_number))[:3]


def col_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def column_number(value: str) -> int:
    letters = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{1,3}", letters):
        raise AtlasError(f"Columna no válida: {value!r}.")
    number = 0
    for character in letters:
        number = number * 26 + ord(character) - 64
    if number > 16384:
        raise AtlasError("La columna excede el límite XFD de una hoja de cálculo.")
    return number


def configure_target_range(value: str) -> str:
    """Configura el bloque mensual de ocho columnas sin ampliar el alcance."""
    match = re.fullmatch(
        r"\s*([A-Za-z]{1,3})\s*(?::\s*([A-Za-z]{1,3})\s*)?", str(value or "")
    )
    if not match:
        raise AtlasError("Escriba un rango como AK:AR o únicamente la primera columna.")
    first = column_number(match.group(1))
    expected_last = first + 7
    if expected_last > 16384:
        raise AtlasError("El bloque de ocho columnas excede el límite XFD.")
    if match.group(2) and column_number(match.group(2)) != expected_last:
        raise AtlasError(
            f"El insertador requiere exactamente ocho columnas consecutivas: "
            f"{col_letter(first)}:{col_letter(expected_last)}."
        )

    definitions = (
        ("(CARTA) Total de impresiones", "principal"),
        ("(OFICIO) Total de impresiones equivalentes", "equivalente"),
        ("Hojas ambas caras", "duplex"),
        ("Eventos de atasco", "atascos"),
        ("Total Escaneos", "escaneos"),
        ("Total de copias", "copias"),
        ("Impresiones a color", "color"),
        ("Total Digitalizaciones", "digitalizaciones"),
    )
    configured = tuple(
        (col_letter(first + offset), first + offset, label, key)
        for offset, (label, key) in enumerate(definitions)
    )
    global TARGET_FIRST_COL, TARGET_LAST_COL, TARGETS
    TARGET_FIRST_COL = first
    TARGET_LAST_COL = expected_last
    TARGETS = configured
    TARGET_BY_KEY.clear()
    TARGET_BY_KEY.update(
        {key: (letter, col, label) for letter, col, label, key in configured}
    )
    TARGET_COLS.clear()
    TARGET_COLS.update(range(first, expected_last + 1))
    AUTHORIZED_WRITE_COLS.clear()
    AUTHORIZED_WRITE_COLS.update(TARGET_COLS)
    return f"{col_letter(first)}:{col_letter(expected_last)}"


def configure_target_columns(value: str) -> str:
    """Configure one to eight logical targets, allowing gaps.

    Accepted forms are a legacy range (``AK:AR``), one starting column (``AK``),
    or one to eight comma-separated entries in FIELD_DEFINITIONS order. Missing
    trailing fields and ``-`` entries are disabled.
    """
    raw = str(value or "").strip()
    if "," not in raw and ";" not in raw:
        return configure_target_range(raw)
    parts = [part.strip().upper() for part in re.split(r"[,;]", raw)]
    if not 1 <= len(parts) <= len(FIELD_DEFINITIONS):
        raise AtlasError(
            "Indique entre una y ocho columnas destino: impresiones, equivalentes, "
            "dúplex, atascos, escaneos, copias, color y digitalizaciones."
        )
    configured = []
    used: set[int] = set()
    for (key, label), token in zip(FIELD_DEFINITIONS, parts):
        if token in {"", "-", "—", "NO", "N/A"}:
            continue
        col = column_number(token)
        if col in used:
            raise AtlasError(f"La columna {token} fue asignada a más de un contador.")
        used.add(col)
        configured.append((col_letter(col), col, label, key))
    if not configured:
        raise AtlasError("Debe habilitar al menos una columna destino.")
    global TARGET_FIRST_COL, TARGET_LAST_COL, TARGETS
    TARGETS = tuple(configured)
    TARGET_FIRST_COL = min(used)
    TARGET_LAST_COL = max(used)
    TARGET_BY_KEY.clear()
    TARGET_BY_KEY.update({key: (letter, col, label) for letter, col, label, key in TARGETS})
    TARGET_COLS.clear()
    TARGET_COLS.update(used)
    AUTHORIZED_WRITE_COLS.clear()
    AUTHORIZED_WRITE_COLS.update(used)
    return target_range_label()


def target_range_label() -> str:
    columns = [TARGET_BY_KEY[key][0] if key in TARGET_BY_KEY else "-" for key, _ in FIELD_DEFINITIONS]
    while columns and columns[-1] == "-":
        columns.pop()
    enabled = [column for column in columns if column != "-"]
    if enabled and len(enabled) == 8 and all(
        column_number(column) == column_number(enabled[0]) + offset
        for offset, column in enumerate(enabled)
    ):
        return f"{enabled[0]}:{enabled[-1]}"
    return ",".join(columns)


def configure_targets_from_master(
    document: "ODSDocument | XLSXDocument",
    sheet: ET.Element,
    header_row: int,
    excluded_cols: Optional[set[int]] = None,
) -> str:
    """Map destination fields from the selected worksheet's real headers."""
    row = document.get_row(sheet, header_row)
    configured = []
    used: set[int] = set()
    excluded_cols = set(excluded_cols or ())
    for key, label in FIELD_DEFINITIONS:
        candidates: list[tuple[int, int]] = []
        for col in range(1, 257):
            if col in excluded_cols:
                continue
            score = base_field_score(key, document.cell_value(document.get_cell(row, col)))
            if score and col not in used:
                candidates.append((score, col))
        if candidates:
            score, col = max(candidates, key=lambda item: (item[0], -item[1]))
            if score >= 60:
                used.add(col)
                configured.append((col_letter(col), col, label, key))
    if not configured:
        raise AtlasError(
            "No se reconocieron columnas destino por sus encabezados. Indíquelas manualmente."
        )
    global TARGET_FIRST_COL, TARGET_LAST_COL, TARGETS
    TARGETS = tuple(configured)
    TARGET_FIRST_COL = min(used)
    TARGET_LAST_COL = max(used)
    TARGET_BY_KEY.clear()
    TARGET_BY_KEY.update({key: (letter, col, label) for letter, col, label, key in TARGETS})
    TARGET_COLS.clear()
    TARGET_COLS.update(used)
    AUTHORIZED_WRITE_COLS.clear()
    AUTHORIZED_WRITE_COLS.update(used)
    return target_range_label()


def configure_targets_without_reserved_location(
    target_spec: str,
    location_col: int,
) -> str:
    """Configure a manual mapping while reserving the equipment-location column.

    A user can reasonably type ``P,R,S,V,W`` after enabling location updates,
    assuming P belongs in the combined mapping.  P is not a counter, however.
    Remove that token and shift the remaining counter mapping to ``R,S,V,W``
    instead of cancelling the entire verified-copy operation.
    """
    raw = str(target_spec or "").strip()
    location_letter = col_letter(location_col)
    if "," in raw or ";" in raw:
        parts = [part.strip().upper() for part in re.split(r"[,;]", raw)]
        filtered = [part for part in parts if part != location_letter]
        if not filtered:
            raise AtlasError(
                f"El mapeo solo contiene {location_letter}, que corresponde a Ubicación de Equipo. "
                "Indique las columnas de contadores, por ejemplo R,S,V,W."
            )
        return configure_target_columns(",".join(filtered))

    configure_target_columns(raw)
    if location_col in TARGET_COLS:
        raise AtlasError(
            f"La columna {location_letter} corresponde a Ubicación de Equipo y no puede usarse "
            "también como contador. Indique únicamente las columnas de contadores."
        )
    return target_range_label()


def is_blank_value(value: Any) -> bool:
    """Verdadero únicamente para una celda realmente vacía."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def parse_number(value: Any) -> Optional[float | int]:
    """Interpreta contadores sin confundir separadores de miles con decimales.

    Los contadores equivalentes pueden incluir una fracción decimal, pero una
    agrupación de tres dígitos (19.346 o 19,346) se interpreta como miles.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    raw = str(value).strip()
    if not raw or normalize_text(raw) in {"n a", "na", "null", "none", "sin dato", "no disponible", "-"}:
        return None
    text = raw.replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text or text == "-" or text.startswith("-"):
        return None

    if "," in text and "." in text:
        # El último separador se considera decimal y el otro, agrupador.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        pieces = text.split(",")
        if len(pieces) > 2 and all(len(piece) == 3 for piece in pieces[1:]):
            text = "".join(pieces)
        elif len(pieces) == 2 and len(pieces[1]) == 3 and 1 <= len(pieces[0]) <= 3:
            text = "".join(pieces)
        elif len(pieces) == 2:
            text = pieces[0] + "." + pieces[1]
        else:
            return None
    elif "." in text:
        pieces = text.split(".")
        if len(pieces) > 2 and all(len(piece) == 3 for piece in pieces[1:]):
            text = "".join(pieces)
        elif len(pieces) == 2 and len(pieces[1]) == 3 and 1 <= len(pieces[0]) <= 3:
            text = "".join(pieces)
        elif len(pieces) > 2:
            return None

    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0:
        return None
    return int(number) if number.is_integer() else number

def numeric_equal(a: Any, b: Any) -> bool:
    pa, pb = parse_number(a), parse_number(b)
    if pa is None or pb is None:
        return pa is None and pb is None
    return abs(float(pa) - float(pb)) < 1e-9


def display_number(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return ""
    if isinstance(number, int):
        return str(number)
    return f"{number:g}"


def apply_serial_overrides(
    report: "TableData",
    mapping: "FieldMapping",
    serial_overrides: Optional[dict[str, str]],
) -> "TableData":
    """Return a report copy with explicit user-reviewed serial corrections."""
    cleaned = {
        normalize_serial(original): str(replacement or "").strip()
        for original, replacement in (serial_overrides or {}).items()
        if normalize_serial(original) and normalize_serial(replacement)
    }
    if not cleaned:
        return report

    rows: list[list[Any]] = []
    for source_row in report.rows:
        row = list(source_row)
        if mapping.serial_col < len(row):
            original_key = normalize_serial(row[mapping.serial_col])
            replacement = cleaned.get(original_key)
            if replacement:
                row[mapping.serial_col] = replacement
        rows.append(row)
    return TableData(
        source_path=report.source_path,
        sheet_name=report.sheet_name,
        header_row=report.header_row,
        headers=list(report.headers),
        rows=rows,
        source_record_count=report.source_record_count,
        source_unique_count=report.source_unique_count,
    )


@dataclass
class TableData:
    source_path: Path
    sheet_name: str
    header_row: int
    headers: list[str]
    rows: list[list[Any]]
    source_record_count: int = 0
    source_unique_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldMapping:
    serial_col: int
    fields: dict[str, int]
    source_headers: dict[str, str]
    unmapped: list[str]


@dataclass(frozen=True)
class MasterLayout:
    header_row: int
    serial_col: int
    locality_col: int
    first_row: int
    last_row: int
    validation_mode: str
    status_col: int = 0
    equipment_location_col: int = 0
    counter_date_col: int = 0
    floor_col: int = 0
    ip_col: int = 0


@dataclass
class MasterRecord:
    row_number: int
    serial_raw: str
    serial_key: str
    locality: str
    current_values: dict[str, Any]
    formula_fields: set[str] = field(default_factory=set)
    current_status: Any = ""
    status_has_formula: bool = False
    current_location: Any = ""
    location_has_formula: bool = False
    current_counter_date: Any = ""
    counter_date_has_formula: bool = False
    current_floor: Any = ""
    floor_has_formula: bool = False
    current_ip: Any = ""
    ip_has_formula: bool = False


@dataclass
class FieldDecision:
    key: str
    target_letter: str
    target_label: str
    source_header: str
    source_value: Any
    existing_value: Any
    action: str  # escribir | sobrescribir | escribir_cero | igual | conflicto | conflicto_fuentes | valor_invalido | valor_maestro_invalido | sin_dato | formula | conservar


@dataclass
class MatchDecision:
    report_row: int
    serial_raw: str
    serial_key: str
    master_row: Optional[int]
    status: str
    details: str
    fields: list[FieldDecision] = field(default_factory=list)
    matched_serial_raw: str = ""
    approximate_match: bool = False
    source_names: str = ""
    operation_status_action: str = "conservar"  # escribir | igual | conservar | formula
    operation_status_existing: Any = ""
    operation_status_value: str = STATUS_VALUE
    has_positive_counter: bool = False
    creates_master_row: bool = False
    location_action: str = "conservar"  # escribir | sobrescribir | igual | conservar | formula | sin_dependencia | conflicto_fuentes
    location_existing: Any = ""
    location_value: str = ""
    counter_date_action: str = "conservar"
    counter_date_existing: Any = ""
    counter_date_value: str = ""
    floor_action: str = "conservar"
    floor_existing: Any = ""
    floor_value: str = ""
    ip_action: str = "conservar"
    ip_existing: Any = ""
    ip_value: str = ""
    atlas_ip_action: str = "conservar"
    atlas_ip_existing: Any = ""
    atlas_ip_value: str = ""

    @property
    def counter_writable_count(self) -> int:
        return sum(1 for item in self.fields if item.action in {"escribir", "sobrescribir", "escribir_cero"})

    @property
    def writable_count(self) -> int:
        auxiliary = (self.location_action, self.counter_date_action, self.floor_action, self.ip_action)
        return self.counter_writable_count + sum(action in {"escribir", "sobrescribir"} for action in auxiliary)

    @property
    def conflict_count(self) -> int:
        return sum(1 for item in self.fields if item.action in {"conflicto", "conflicto_fuentes"})


@dataclass
class AnalysisResult:
    master_path: Path
    report_path: Path
    master_sheet: str
    master_layout: MasterLayout
    report_sheet: str
    report_header_row: int
    mapping: FieldMapping
    overwrite_existing: bool
    decisions: list[MatchDecision]
    master_records: dict[str, MasterRecord]
    report_duplicate_serials: set[str]
    master_duplicate_serials: set[str]
    source_record_count: int = 0
    source_unique_count: int = 0
    location_mode: str = "off"
    auxiliary_mode: str = "off"
    import_missing_ips: bool = False
    atlas_database_path: Optional[Path] = None

    def counts(self) -> dict[str, int]:
        counters = Counter(item.status for item in self.decisions)
        counters["report_rows"] = len(self.decisions)
        counters["matched"] = sum(1 for d in self.decisions if d.master_row is not None)
        counters["writable_equipment"] = sum(1 for d in self.decisions if d.writable_count > 0)
        counters["writable_cells"] = sum(d.writable_count for d in self.decisions)
        counters["zero_fill_cells"] = sum(
            1 for d in self.decisions for item in d.fields if item.action == "escribir_cero"
        )
        counters["conflict_cells"] = sum(
            1 for d in self.decisions for item in d.fields
            if item.action in {"conflicto", "conflicto_fuentes"}
        )
        counters["unmapped_fields"] = len(self.mapping.unmapped)
        counters["discrepancies"] = len(self.discrepancy_rows())
        counters["new_master_rows"] = sum(1 for d in self.decisions if d.creates_master_row)
        counters["status_updates"] = sum(
            1 for d in self.decisions if d.operation_status_action == "escribir"
        )
        counters["location_updates"] = sum(
            1 for d in self.decisions if d.location_action in {"escribir", "sobrescribir"}
        )
        counters["location_replacements"] = sum(
            1 for d in self.decisions if d.location_action == "sobrescribir"
        )
        counters["missing_dependencies"] = sum(
            1 for d in self.decisions if d.location_action == "sin_dependencia"
        )
        counters["date_updates"] = sum(1 for d in self.decisions if d.counter_date_action == "escribir")
        counters["floor_updates"] = sum(1 for d in self.decisions if d.floor_action == "escribir")
        counters["ip_updates"] = sum(1 for d in self.decisions if d.ip_action == "escribir")
        counters["atlas_ip_imports"] = sum(1 for d in self.decisions if d.atlas_ip_action == "importar")
        counters["ip_conflicts"] = sum(1 for d in self.decisions if d.ip_action == "conflicto")
        return dict(counters)

    def discrepancy_rows(self) -> list[dict[str, Any]]:
        """Devuelve una fila auditable por cada condición que requiere revisión."""
        rows: list[dict[str, Any]] = []
        decision_types = {
            "serie_vacia": "SERIE_VACIA",
            "no_encontrado": "SERIE_NO_ENCONTRADA",
            "duplicado_reporte": "SERIE_DUPLICADA_EN_REPORTE",
            "duplicado_maestro": "SERIE_DUPLICADA_EN_MAESTRO",
            "sin_datos_validos": "SIN_CONTADORES_VALIDOS",
            "posible_serie_mal_escrita": "POSIBLE_SERIE_MAL_ESCRITA_O_DUPLICADA",
            "nueva_fila_con_advertencia": "ALTA_AUTORIZADA_DE_SERIE_PARECIDA",
        }
        action_types = {
            "conflicto": "VALOR_EXISTENTE_DIFERENTE",
            "conflicto_fuentes": "VALORES_DIFERENTES_ENTRE_FUENTES",
            "formula": "CELDA_PROTEGIDA_POR_FORMULA",
            "valor_invalido": "VALOR_DE_REPORTE_INVALIDO",
            "valor_maestro_invalido": "VALOR_MAESTRO_NO_NUMERICO",
            "sobrescribir": "VALOR_EXISTENTE_REEMPLAZADO",
        }
        for decision in self.decisions:
            base = {
                "fuentes": decision.source_names or self.report_path.name,
                "fila_reporte": decision.report_row,
                "serie_reporte": decision.serial_raw,
                "serie_normalizada": decision.serial_key,
                "serie_maestra": decision.matched_serial_raw,
                "fila_maestra": decision.master_row or "",
            }
            if decision.status in decision_types:
                rows.append({**base, "tipo": decision_types[decision.status], "campo": "Número de serie",
                             "celda": "", "valor_reporte": decision.serial_raw, "valor_maestro": "",
                             "accion": "REVISAR_MANUALMENTE", "detalle": decision.details})
            for item in decision.fields:
                discrepancy_type = action_types.get(item.action)
                if discrepancy_type is None:
                    continue
                cell = f"{item.target_letter}{decision.master_row}" if decision.master_row else item.target_letter
                rows.append({**base, "tipo": discrepancy_type, "campo": item.target_label,
                             "celda": cell, "valor_reporte": display_number(item.source_value) or str(item.source_value or ""),
                             "valor_maestro": display_number(item.existing_value) or str(item.existing_value or ""),
                             "accion": item.action.upper(), "detalle": item.source_header})
            if decision.location_action in {"formula", "conflicto_fuentes", "sobrescribir"}:
                location_col = self.master_layout.equipment_location_col
                rows.append({
                    **base,
                    "tipo": (
                        "UBICACION_PROTEGIDA" if decision.location_action == "formula"
                        else "UBICACION_REEMPLAZADA" if decision.location_action == "sobrescribir"
                        else "UBICACIONES_DIFERENTES_ENTRE_FUENTES"
                    ),
                    "campo": "Ubicación de Equipo",
                    "celda": f"{col_letter(location_col)}{decision.master_row}" if location_col and decision.master_row else "",
                    "valor_reporte": decision.location_value,
                    "valor_maestro": str(decision.location_existing or ""),
                    "accion": decision.location_action.upper(),
                    "detalle": decision.details,
                })
            if decision.ip_action == "conflicto":
                ip_col = self.master_layout.ip_col
                rows.append({
                    **base,
                    "tipo": "IP_DIFERENTE_ENTRE_ATLAS_Y_HOJA",
                    "campo": "Dirección IP",
                    "celda": f"{col_letter(ip_col)}{decision.master_row}" if ip_col and decision.master_row else "",
                    "valor_reporte": decision.ip_value,
                    "valor_maestro": str(decision.ip_existing or ""),
                    "accion": "REVISAR_MANUALMENTE",
                    "detalle": "Atlas conserva ambos valores sin reemplazarlos automáticamente.",
                })
        return rows

    def location_updates(self) -> dict[int, str]:
        return {
            decision.master_row: decision.location_value
            for decision in self.decisions
            if decision.master_row is not None
            and decision.location_action in {"escribir", "sobrescribir"}
            and decision.location_value
        }

    def auxiliary_updates(self) -> dict[int, dict[str, str]]:
        result: dict[int, dict[str, str]] = defaultdict(dict)
        for decision in self.decisions:
            if decision.master_row is None:
                continue
            if decision.counter_date_action == "escribir":
                result[decision.master_row]["counter_date"] = decision.counter_date_value
            if decision.floor_action == "escribir":
                result[decision.master_row]["floor"] = decision.floor_value
            if decision.ip_action == "escribir":
                result[decision.master_row]["ip"] = decision.ip_value
        return dict(result)

    def atlas_ip_updates(self) -> dict[str, str]:
        return {
            decision.serial_key: decision.atlas_ip_value
            for decision in self.decisions
            if decision.atlas_ip_action == "importar" and decision.atlas_ip_value
        }

    def updates(self) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = defaultdict(dict)
        for decision in self.decisions:
            if decision.master_row is None:
                continue
            for field_decision in decision.fields:
                if field_decision.action in {"escribir", "sobrescribir", "escribir_cero"}:
                    result[decision.master_row][field_decision.key] = field_decision.source_value
        return dict(result)

    def status_updates(self) -> dict[int, str]:
        """Return reviewed En Operación changes for the detected status column."""
        return {
            decision.master_row: STATUS_VALUE
            for decision in self.decisions
            if decision.master_row is not None and decision.operation_status_action == "escribir"
        }


class ODSDocument:
    """Lector/escritor ODS de alcance controlado, basado en XML del estándar ODF."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.suffix.lower() != ".ods":
            raise AtlasError("La hoja maestra debe estar en formato ODS.")
        if not self.path.exists():
            raise AtlasError(f"No existe el archivo maestro: {self.path}")
        try:
            with zipfile.ZipFile(self.path, "r") as archive:
                self.infos = archive.infolist()
                self.members = {info.filename: archive.read(info.filename) for info in self.infos}
        except (OSError, zipfile.BadZipFile) as exc:
            raise AtlasError(f"No se pudo abrir el ODS: {exc}") from exc
        if "content.xml" not in self.members:
            raise AtlasError("El archivo ODS no contiene content.xml.")
        try:
            self.root = ET.fromstring(self.members["content.xml"])
        except ET.ParseError as exc:
            raise AtlasError(f"El contenido XML del ODS no es válido: {exc}") from exc

    def sheet_names(self) -> list[str]:
        spreadsheet = self.root.find(".//office:spreadsheet", NS)
        if spreadsheet is None:
            return []
        return [table.get(T + "name", "") for table in spreadsheet.findall("table:table", NS)]

    @staticmethod
    def sheet_name(sheet: ET.Element) -> str:
        return sheet.get(T + "name", "")

    def find_sheet(self, candidates: Iterable[str] = MASTER_SHEET_CANDIDATES) -> ET.Element:
        spreadsheet = self.root.find(".//office:spreadsheet", NS)
        if spreadsheet is None:
            raise AtlasError("No se encontró el libro de cálculo dentro del ODS.")
        tables = spreadsheet.findall("table:table", NS)
        candidate_norm = {normalize_text(name) for name in candidates}
        for table in tables:
            if normalize_text(table.get(T + "name", "")) in candidate_norm:
                return table
        for table in tables:
            name_norm = normalize_text(table.get(T + "name", ""))
            if "consumo" in name_norm and "impresion" in name_norm and "mono" in name_norm:
                return table
        available = ", ".join(self.sheet_names())
        raise AtlasError(
            "No se encontró la hoja de consumo de impresión mono. "
            f"Hojas disponibles: {available}"
        )

    @staticmethod
    def _row_repeat(row: ET.Element) -> int:
        return int(row.get(T + "number-rows-repeated", "1"))

    @staticmethod
    def _cell_repeat(cell: ET.Element) -> int:
        return int(cell.get(T + "number-columns-repeated", "1"))

    @staticmethod
    def _set_repeat(element: ET.Element, attr: str, count: int) -> None:
        if count <= 1:
            element.attrib.pop(attr, None)
        else:
            element.set(attr, str(count))

    def get_row(self, sheet: ET.Element, logical_row: int, split: bool = False) -> ET.Element:
        if logical_row < 1:
            raise AtlasError("Número de fila inválido.")
        current = 0
        children = list(sheet)
        for physical_index, child in enumerate(children):
            if child.tag != T + "table-row":
                continue
            repeat = self._row_repeat(child)
            start = current + 1
            end = current + repeat
            if start <= logical_row <= end:
                if repeat == 1 or not split:
                    return child
                offset = logical_row - start
                replacements: list[ET.Element] = []
                if offset > 0:
                    before = copy.deepcopy(child)
                    self._set_repeat(before, T + "number-rows-repeated", offset)
                    replacements.append(before)
                target = copy.deepcopy(child)
                self._set_repeat(target, T + "number-rows-repeated", 1)
                replacements.append(target)
                after_count = repeat - offset - 1
                if after_count > 0:
                    after = copy.deepcopy(child)
                    self._set_repeat(after, T + "number-rows-repeated", after_count)
                    replacements.append(after)
                sheet.remove(child)
                for replacement in reversed(replacements):
                    sheet.insert(physical_index, replacement)
                return target
            current = end
        raise AtlasError(f"La hoja no contiene la fila lógica {logical_row}.")

    def get_cell(self, row: ET.Element, logical_col: int, split: bool = False) -> ET.Element:
        if logical_col < 1:
            raise AtlasError("Número de columna inválido.")
        current = 0
        children = list(row)
        for physical_index, child in enumerate(children):
            if child.tag not in {T + "table-cell", T + "covered-table-cell"}:
                continue
            repeat = self._cell_repeat(child)
            start = current + 1
            end = current + repeat
            if start <= logical_col <= end:
                if repeat == 1 or not split:
                    return child
                offset = logical_col - start
                replacements: list[ET.Element] = []
                if offset > 0:
                    before = copy.deepcopy(child)
                    self._set_repeat(before, T + "number-columns-repeated", offset)
                    replacements.append(before)
                target = copy.deepcopy(child)
                self._set_repeat(target, T + "number-columns-repeated", 1)
                replacements.append(target)
                after_count = repeat - offset - 1
                if after_count > 0:
                    after = copy.deepcopy(child)
                    self._set_repeat(after, T + "number-columns-repeated", after_count)
                    replacements.append(after)
                row.remove(child)
                for replacement in reversed(replacements):
                    row.insert(physical_index, replacement)
                return target
            current = end
        raise AtlasError(
            f"La fila no contiene la columna lógica {col_letter(logical_col)}. "
            "La aplicación no agregará columnas nuevas."
        )

    @staticmethod
    def cell_formula(cell: ET.Element) -> str:
        return cell.get(T + "formula", "")

    @staticmethod
    def cell_value(cell: ET.Element) -> Any:
        value_type = cell.get(O + "value-type", "")
        if value_type in {"float", "currency", "percentage"}:
            raw = cell.get(O + "value")
            if raw is not None:
                return parse_number(raw)
        if value_type == "boolean":
            return cell.get(O + "boolean-value") == "true"
        for attr in (O + "string-value", O + "date-value", O + "time-value"):
            if attr in cell.attrib:
                return cell.attrib[attr]
        paragraphs = []
        for paragraph in cell.findall(X + "p"):
            text = "".join(paragraph.itertext()).strip()
            if text:
                paragraphs.append(text)
        if paragraphs:
            return "\n".join(paragraphs)
        raw = cell.get(O + "value")
        return parse_number(raw) if raw is not None else ""

    @staticmethod
    def set_numeric_value(cell: ET.Element, value: Any) -> None:
        if cell.get(T + "formula"):
            raise AtlasError("Se bloqueó un intento de modificar una fórmula.")
        number = parse_number(value)
        if number is None:
            raise AtlasError(f"Valor de contador inválido: {value!r}")
        cell.set(O + "value-type", "float")
        cell.set(O + "value", display_number(number))
        for attr in (
            O + "string-value", O + "date-value", O + "time-value",
            O + "boolean-value", O + "currency",
        ):
            cell.attrib.pop(attr, None)
        for paragraph in list(cell.findall(X + "p")):
            cell.remove(paragraph)
        paragraph = ET.Element(X + "p")
        paragraph.text = display_number(number)
        cell.append(paragraph)

    @staticmethod
    def set_text_value(cell: ET.Element, value: Any) -> None:
        if cell.get(T + "formula"):
            raise AtlasError("Se bloqueó un intento de modificar una fórmula.")
        text = str(value or "").strip()
        if not text:
            raise AtlasError("El estado de operación no puede quedar vacío.")
        cell.set(O + "value-type", "string")
        cell.set(O + "string-value", text)
        for attr in (
            O + "value", O + "date-value", O + "time-value",
            O + "boolean-value", O + "currency",
        ):
            cell.attrib.pop(attr, None)
        for paragraph in list(cell.findall(X + "p")):
            cell.remove(paragraph)
        paragraph = ET.Element(X + "p")
        paragraph.text = text
        cell.append(paragraph)

    def formula_snapshot(self) -> tuple[str, ...]:
        """Devuelve las fórmulas por coordenada lógica, no por nodo XML físico.

        Al escribir una celda vacía puede ser necesario dividir un nodo ODF con
        `number-columns-repeated`. Esa división no cambia ninguna columna lógica,
        pero sí el número de nodos XML. Por eso la verificación usa fila/columna
        lógica y la fórmula textual exacta.
        """
        formulas = []
        for table in self.root.findall(".//table:table", NS):
            sheet_name = table.get(T + "name", "")
            logical_row = 0
            for row in table.findall("table:table-row", NS):
                row_repeat = self._row_repeat(row)
                logical_col = 0
                row_formulas: list[tuple[int, str]] = []
                for cell in list(row):
                    if cell.tag not in {T + "table-cell", T + "covered-table-cell"}:
                        continue
                    cell_repeat = self._cell_repeat(cell)
                    formula = cell.get(T + "formula")
                    if formula:
                        if cell_repeat != 1:
                            # Una fórmula repetida representa la misma fórmula en
                            # varias columnas lógicas. Se registra cada dirección.
                            for offset in range(cell_repeat):
                                row_formulas.append((logical_col + offset + 1, formula))
                        else:
                            row_formulas.append((logical_col + 1, formula))
                    logical_col += cell_repeat
                for row_offset in range(row_repeat):
                    row_number = logical_row + row_offset + 1
                    for col_number, formula in row_formulas:
                        formulas.append(f"{sheet_name}|{row_number}|{col_number}|{formula}")
                logical_row += row_repeat
        return tuple(formulas)

    def save(self, output_path: Path) -> None:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".ods":
            raise AtlasError("El archivo de salida debe conservar la extensión .ods.")
        if os.path.abspath(output_path) == os.path.abspath(self.path):
            raise AtlasError("No se permite sobrescribir el archivo maestro original.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = ET.tostring(self.root, encoding="utf-8", xml_declaration=True)

        temp_path = output_path.with_name(output_path.name + ".tmp")
        try:
            with zipfile.ZipFile(temp_path, "w") as out_zip:
                for info in self.infos:
                    data = content if info.filename == "content.xml" else self.members[info.filename]
                    out_zip.writestr(info, data)
            # Verificación básica del contenedor antes de sustituir el destino.
            with zipfile.ZipFile(temp_path, "r") as check_zip:
                bad = check_zip.testzip()
                if bad:
                    raise AtlasError(f"La copia ODS generada está dañada en: {bad}")
                if check_zip.read("mimetype") != self.members.get("mimetype", b""):
                    raise AtlasError("La copia ODS no conservó su tipo MIME.")
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)



XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XM = "{%s}" % XLSX_MAIN_NS
XR = "{%s}" % XLSX_REL_NS
XPR = "{%s}" % XLSX_PACKAGE_REL_NS


def register_namespaces_from_xml(raw: bytes) -> None:
    """Conserva los prefijos usados por Excel al volver a serializar una hoja."""
    for match in re.finditer(rb'xmlns(?::([A-Za-z_][A-Za-z0-9_.-]*))?=["\']([^"\']+)["\']', raw[:20000]):
        prefix = (match.group(1) or b"").decode("utf-8", "ignore")
        uri = match.group(2).decode("utf-8", "ignore")
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass


class XLSXDocument:
    """Editor OOXML de alcance mínimo para valores autorizados exclusivamente en AK–AR."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.suffix.lower() != ".xlsx":
            raise AtlasError("La hoja maestra XLSX debe conservar la extensión .xlsx.")
        if not self.path.exists():
            raise AtlasError(f"No existe el archivo maestro: {self.path}")
        try:
            with zipfile.ZipFile(self.path, "r") as archive:
                self.infos = archive.infolist()
                self.members = {info.filename: archive.read(info.filename) for info in self.infos}
        except (OSError, zipfile.BadZipFile) as exc:
            raise AtlasError(f"No se pudo abrir el XLSX: {exc}") from exc

        for required in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if required not in self.members:
                raise AtlasError(f"El XLSX no contiene {required}.")
        register_namespaces_from_xml(self.members["xl/workbook.xml"])
        try:
            self.workbook_root = ET.fromstring(self.members["xl/workbook.xml"])
            self.rels_root = ET.fromstring(self.members["xl/_rels/workbook.xml.rels"])
        except ET.ParseError as exc:
            raise AtlasError(f"La estructura XML del XLSX no es válida: {exc}") from exc

        self.shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in self.members:
            register_namespaces_from_xml(self.members["xl/sharedStrings.xml"])
            try:
                shared_root = ET.fromstring(self.members["xl/sharedStrings.xml"])
                for item in shared_root.findall(XM + "si"):
                    self.shared_strings.append("".join(node.text or "" for node in item.iter(XM + "t")))
            except ET.ParseError:
                self.shared_strings = []

        # Se conserva y, solo cuando es necesario para mostrar un cero, se ajusta
        # únicamente el formato numérico de la celda. El resto del estilo
        # (bordes, relleno, fuente y alineación) permanece intacto.
        self.styles_path = "xl/styles.xml" if "xl/styles.xml" in self.members else ""
        self.styles_root: Optional[ET.Element] = None
        self._visible_zero_style_cache: dict[tuple[str, str], str] = {}
        self._general_style_cache: dict[str, str] = {}
        if self.styles_path:
            register_namespaces_from_xml(self.members[self.styles_path])
            try:
                self.styles_root = ET.fromstring(self.members[self.styles_path])
            except ET.ParseError:
                self.styles_root = None

        rel_map = {
            rel.get("Id", ""): rel.get("Target", "")
            for rel in self.rels_root.findall(XPR + "Relationship")
        }
        self.sheet_entries: list[tuple[str, str]] = []
        sheets = self.workbook_root.find(XM + "sheets")
        if sheets is not None:
            for item in sheets.findall(XM + "sheet"):
                name = item.get("name", "Hoja")
                target = rel_map.get(item.get(XR + "id", ""), "")
                if not target:
                    continue
                if target.startswith("/"):
                    sheet_path = target.lstrip("/")
                else:
                    sheet_path = posixpath.normpath(posixpath.join("xl", target))
                if sheet_path in self.members:
                    self.sheet_entries.append((name, sheet_path))
        if not self.sheet_entries:
            raise AtlasError("El XLSX no contiene hojas accesibles.")

        self._sheet_roots: dict[str, ET.Element] = {}
        self._root_paths: dict[int, str] = {}
        self._root_names: dict[int, str] = {}
        self._row_sheets: dict[int, ET.Element] = {}

    def _load_sheet(self, name: str, path: str) -> ET.Element:
        if path not in self._sheet_roots:
            raw = self.members[path]
            register_namespaces_from_xml(raw)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise AtlasError(f"La hoja {name!r} del XLSX no es válida: {exc}") from exc
            self._sheet_roots[path] = root
            self._root_paths[id(root)] = path
            self._root_names[id(root)] = name
        return self._sheet_roots[path]

    def sheet_names(self) -> list[str]:
        return [name for name, _ in self.sheet_entries]

    def sheet_name(self, sheet: ET.Element) -> str:
        return self._root_names.get(id(sheet), "")

    def find_sheet(self, candidates: Iterable[str] = MASTER_SHEET_CANDIDATES) -> ET.Element:
        candidate_norm = {normalize_text(name) for name in candidates}
        for name, path in self.sheet_entries:
            if normalize_text(name) in candidate_norm:
                return self._load_sheet(name, path)
        for name, path in self.sheet_entries:
            name_norm = normalize_text(name)
            if "consumo" in name_norm and "impresion" in name_norm and "mono" in name_norm:
                return self._load_sheet(name, path)
        raise AtlasError(
            "No se encontró la hoja de consumo de impresión mono. "
            f"Hojas disponibles: {', '.join(self.sheet_names())}"
        )

    @staticmethod
    def _sheet_data(sheet: ET.Element) -> ET.Element:
        sheet_data = sheet.find(XM + "sheetData")
        if sheet_data is None:
            sheet_data = ET.Element(XM + "sheetData")
            insert_at = 0
            children = list(sheet)
            for index, child in enumerate(children):
                if child.tag in {XM + "sheetPr", XM + "dimension", XM + "sheetViews", XM + "sheetFormatPr", XM + "cols"}:
                    insert_at = index + 1
            sheet.insert(insert_at, sheet_data)
        return sheet_data

    def get_row(self, sheet: ET.Element, logical_row: int, split: bool = False) -> ET.Element:
        if logical_row < 1:
            raise AtlasError("Número de fila inválido.")
        sheet_data = self._sheet_data(sheet)
        rows = sheet_data.findall(XM + "row")
        for row in rows:
            if int(row.get("r", "0") or 0) == logical_row:
                self._row_sheets[id(row)] = sheet
                return row
        row = ET.Element(XM + "row", {"r": str(logical_row)})
        insert_at = len(list(sheet_data))
        for index, existing in enumerate(list(sheet_data)):
            if existing.tag == XM + "row" and int(existing.get("r", "0") or 0) > logical_row:
                insert_at = index
                break
        sheet_data.insert(insert_at, row)
        self._row_sheets[id(row)] = sheet
        return row

    def _infer_style(self, sheet: ET.Element, row_number: int, logical_col: int) -> Optional[str]:
        ref_letter = col_letter(logical_col)
        sheet_data = self._sheet_data(sheet)
        best: tuple[int, str] | None = None
        for row in sheet_data.findall(XM + "row"):
            candidate_row = int(row.get("r", "0") or 0)
            if candidate_row == row_number:
                continue
            for cell in row.findall(XM + "c"):
                if xlsx_col_index(cell.get("r", "")) == logical_col and "s" in cell.attrib:
                    distance = abs(candidate_row - row_number)
                    if best is None or distance < best[0]:
                        best = (distance, cell.get("s", ""))
                    break
            if best is not None and best[0] <= 1:
                break
        return best[1] if best else None

    def get_cell(self, row: ET.Element, logical_col: int, split: bool = False) -> ET.Element:
        if logical_col < 1:
            raise AtlasError("Número de columna inválido.")
        row_number = int(row.get("r", "0") or 0)
        reference = f"{col_letter(logical_col)}{row_number}"
        for cell in row.findall(XM + "c"):
            if cell.get("r", "").upper() == reference.upper():
                return cell
        if not split:
            return ET.Element(XM + "c", {"r": reference})
        attrs = {"r": reference}
        sheet = self._row_sheets.get(id(row))
        if sheet is not None:
            style = self._infer_style(sheet, row_number, logical_col)
            if style:
                attrs["s"] = style
        cell = ET.Element(XM + "c", attrs)
        insert_at = len(list(row))
        for index, existing in enumerate(list(row)):
            if existing.tag == XM + "c" and xlsx_col_index(existing.get("r", "")) > logical_col:
                insert_at = index
                break
        row.insert(insert_at, cell)
        return cell

    def _cell_xfs(self) -> Optional[ET.Element]:
        if self.styles_root is None:
            return None
        return self.styles_root.find(XM + "cellXfs")

    def _style_xf(self, style_id: str) -> Optional[ET.Element]:
        try:
            index = int(style_id)
        except (TypeError, ValueError):
            return None
        cell_xfs = self._cell_xfs()
        if cell_xfs is None:
            return None
        styles = cell_xfs.findall(XM + "xf")
        return styles[index] if 0 <= index < len(styles) else None

    def _nearest_existing_zero_style(
        self,
        sheet: ET.Element,
        row_number: int,
        logical_col: int,
    ) -> Optional[str]:
        """Busca un estilo que ya muestre un cero en la misma columna.

        La hoja oficial contiene ceros visibles de capturas anteriores. Se usa
        únicamente su formato numérico, no su relleno ni sus bordes.
        """
        cache_key = (self.sheet_name(sheet), col_letter(logical_col))
        if cache_key in self._visible_zero_style_cache:
            cached = self._visible_zero_style_cache[cache_key]
            return cached or None
        best: tuple[int, str] | None = None
        for row in self._sheet_data(sheet).findall(XM + "row"):
            candidate_row = int(row.get("r", "0") or 0)
            if candidate_row == row_number:
                continue
            for candidate in row.findall(XM + "c"):
                if xlsx_col_index(candidate.get("r", "")) != logical_col:
                    continue
                if self.cell_formula(candidate):
                    break
                if parse_number(self.cell_value(candidate)) == 0 and candidate.get("s") is not None:
                    distance = abs(candidate_row - row_number)
                    if best is None or distance < best[0]:
                        best = (distance, candidate.get("s", ""))
                break
        result = best[1] if best else ""
        self._visible_zero_style_cache[cache_key] = result
        return result or None

    def _clone_style_with_numfmt(self, original_style: str, number_style: Optional[str]) -> Optional[str]:
        """Clona un estilo conservando todo salvo su formato numérico."""
        cell_xfs = self._cell_xfs()
        original = self._style_xf(original_style)
        if cell_xfs is None or original is None:
            return None
        source_numfmt = self._style_xf(number_style) if number_style is not None else None
        num_fmt_id = source_numfmt.get("numFmtId", "0") if source_numfmt is not None else "0"
        apply_number = source_numfmt.get("applyNumberFormat") if source_numfmt is not None else None
        cache_key = f"{original_style}|{num_fmt_id}|{apply_number or ''}"
        cached = self._general_style_cache.get(cache_key)
        if cached is not None:
            return cached
        clone = copy.deepcopy(original)
        clone.set("numFmtId", num_fmt_id)
        if apply_number is None:
            clone.attrib.pop("applyNumberFormat", None)
        else:
            clone.set("applyNumberFormat", apply_number)
        cell_xfs.append(clone)
        cell_xfs.set("count", str(len(cell_xfs.findall(XM + "xf"))))
        new_style = str(len(cell_xfs.findall(XM + "xf")) - 1)
        self._general_style_cache[cache_key] = new_style
        return new_style

    def ensure_zero_visible(
        self,
        sheet: ET.Element,
        row_number: int,
        logical_col: int,
        cell: ET.Element,
    ) -> None:
        """Evita que el formato del XLSX oculte un cero recién insertado.

        No cambia valores, fórmulas, bordes, colores ni alineación. Si la celda
        tiene un formato numérico que deja en blanco los ceros, clona su estilo
        y toma el formato numérico de un cero visible existente en la misma
        columna. Si no existe uno, usa el formato General.
        """
        current_style = cell.get("s")
        if current_style is None:
            return
        visible_style = self._nearest_existing_zero_style(sheet, row_number, logical_col)
        replacement = self._clone_style_with_numfmt(current_style, visible_style)
        if replacement is not None:
            cell.set("s", replacement)

    @staticmethod
    def cell_formula(cell: ET.Element) -> str:
        formula = cell.find(XM + "f")
        if formula is None:
            return ""
        return formula.text or "<fórmula>"

    def cell_value(self, cell: ET.Element) -> Any:
        cell_type = cell.get("t", "")
        value_node = cell.find(XM + "v")
        inline = cell.find(XM + "is")
        if cell_type == "s" and value_node is not None:
            try:
                return self.shared_strings[int(value_node.text or "0")]
            except (ValueError, IndexError):
                return ""
        if cell_type == "inlineStr" and inline is not None:
            return "".join(node.text or "" for node in inline.iter(XM + "t"))
        if cell_type == "str" and value_node is not None:
            return value_node.text or ""
        if cell_type == "b" and value_node is not None:
            return value_node.text == "1"
        if cell_type == "e" and value_node is not None:
            return value_node.text or ""
        if value_node is not None:
            raw = value_node.text or ""
            number = parse_number(raw)
            return number if number is not None else raw
        return ""

    @staticmethod
    def set_numeric_value(cell: ET.Element, value: Any) -> None:
        if cell.find(XM + "f") is not None:
            raise AtlasError("Se bloqueó un intento de modificar una fórmula.")
        number = parse_number(value)
        if number is None:
            raise AtlasError(f"Valor de contador inválido: {value!r}")
        cell.attrib.pop("t", None)
        for child in list(cell):
            if child.tag in {XM + "v", XM + "is"}:
                cell.remove(child)
        value_node = ET.Element(XM + "v")
        value_node.text = display_number(number)
        children = list(cell)
        insert_at = len(children)
        for index, child in enumerate(children):
            if child.tag == XM + "extLst":
                insert_at = index
                break
        cell.insert(insert_at, value_node)

    @staticmethod
    def set_text_value(cell: ET.Element, value: Any) -> None:
        if cell.find(XM + "f") is not None:
            raise AtlasError("Se bloqueó un intento de modificar una fórmula.")
        text = str(value or "").strip()
        if not text:
            raise AtlasError("El estado de operación no puede quedar vacío.")
        cell.set("t", "inlineStr")
        for child in list(cell):
            if child.tag in {XM + "v", XM + "is"}:
                cell.remove(child)
        inline = ET.Element(XM + "is")
        text_node = ET.SubElement(inline, XM + "t")
        text_node.text = text
        children = list(cell)
        insert_at = len(children)
        for index, child in enumerate(children):
            if child.tag == XM + "extLst":
                insert_at = index
                break
        cell.insert(insert_at, inline)

    def formula_snapshot(self) -> tuple[str, ...]:
        formulas: list[str] = []
        for name, path in self.sheet_entries:
            if path in self._sheet_roots:
                root = self._sheet_roots[path]
            else:
                raw = self.members[path]
                register_namespaces_from_xml(raw)
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError:
                    continue
            for cell in root.iter(XM + "c"):
                formula = cell.find(XM + "f")
                if formula is None:
                    continue
                attributes = ";".join(f"{key}={value}" for key, value in sorted(formula.attrib.items()))
                formulas.append(f"{name}|{cell.get('r', '')}|{attributes}|{formula.text or ''}")
        return tuple(formulas)

    def save(self, output_path: Path) -> None:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".xlsx":
            raise AtlasError("El archivo de salida debe conservar la extensión .xlsx.")
        if os.path.abspath(output_path) == os.path.abspath(self.path):
            raise AtlasError("No se permite sobrescribir el archivo maestro original.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        replacements = {
            path: ET.tostring(root, encoding="utf-8", xml_declaration=True)
            for path, root in self._sheet_roots.items()
        }
        if self.styles_path and self.styles_root is not None:
            replacements[self.styles_path] = ET.tostring(
                self.styles_root, encoding="utf-8", xml_declaration=True
            )
        temp_path = output_path.with_name(output_path.name + ".tmp")
        try:
            with zipfile.ZipFile(temp_path, "w") as out_zip:
                for info in self.infos:
                    out_zip.writestr(info, replacements.get(info.filename, self.members[info.filename]))
            with zipfile.ZipFile(temp_path, "r") as check_zip:
                bad = check_zip.testzip()
                if bad:
                    raise AtlasError(f"La copia XLSX generada está dañada en: {bad}")
                for required in ("[Content_Types].xml", "xl/workbook.xml"):
                    if required not in check_zip.namelist():
                        raise AtlasError(f"La copia XLSX no contiene {required}.")
            os.replace(temp_path, output_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)


def open_master_document(path: Path) -> ODSDocument | XLSXDocument:
    suffix = Path(path).suffix.lower()
    if suffix == ".ods":
        return ODSDocument(Path(path))
    if suffix == ".xlsx":
        return XLSXDocument(Path(path))
    raise AtlasError("La hoja maestra debe estar en formato XLSX u ODS.")


def master_sheet_names(path: Path) -> list[str]:
    return open_master_document(Path(path)).sheet_names()


def suggest_master_sheet(path: Path) -> str:
    """Prefer the last worksheet that has a valid serial/locality data layout."""
    document = open_master_document(Path(path))
    names = document.sheet_names()
    for name in reversed(names):
        try:
            sheet = document.find_sheet((name,))
            detect_master_layout(document, sheet)
        except AtlasError:
            continue
        return name
    return names[-1] if names else ""

def iter_ods_rows(table: ET.Element, max_rows: Optional[int] = None, max_cols: int = 80) -> Iterator[tuple[int, list[Any]]]:
    logical_row = 0
    for row in table.findall("table:table-row", NS):
        row_repeat = int(row.get(T + "number-rows-repeated", "1"))
        values: list[Any] = []
        for cell in list(row):
            if cell.tag not in {T + "table-cell", T + "covered-table-cell"}:
                continue
            repeat = int(cell.get(T + "number-columns-repeated", "1"))
            value = ODSDocument.cell_value(cell)
            remaining = max_cols - len(values)
            if remaining <= 0:
                break
            values.extend([value] * min(repeat, remaining))
        values.extend([""] * (max_cols - len(values)))
        for _ in range(row_repeat):
            logical_row += 1
            if max_rows is not None and logical_row > max_rows:
                return
            yield logical_row, list(values)


def read_ods_tables(path: Path) -> list[TableData]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            root = ET.fromstring(archive.read("content.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise AtlasError(f"No se pudo leer el reporte ODS: {exc}") from exc
    spreadsheet = root.find(".//office:spreadsheet", NS)
    if spreadsheet is None:
        raise AtlasError("El reporte ODS no contiene hojas de cálculo.")
    tables = []
    for table in spreadsheet.findall("table:table", NS):
        name = table.get(T + "name", "Hoja")
        rows = [values for _, values in iter_ods_rows(table, max_rows=50000, max_cols=100)]
        tables.extend(detect_header_candidates(path, name, rows))
    return tables


def xlsx_col_index(reference: str) -> int:
    match = re.match(r"([A-Za-z]+)", reference or "")
    if not match:
        return 0
    result = 0
    for char in match.group(1).upper():
        result = result * 26 + ord(char) - 64
    return result


def read_xlsx_tables(path: Path) -> list[TableData]:
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise AtlasError(f"No se pudo abrir el reporte XLSX: {exc}") from exc
    with archive:
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (KeyError, ET.ParseError) as exc:
            raise AtlasError(f"El XLSX no tiene una estructura válida: {exc}") from exc

        main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        M = "{%s}" % main_ns
        R = "{%s}" % rel_ns
        PR = "{%s}" % package_rel_ns

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            try:
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in shared_root.findall(M + "si"):
                    shared_strings.append("".join(node.text or "" for node in item.iter(M + "t")))
            except ET.ParseError:
                shared_strings = []

        rel_map = {}
        for rel in rels.findall(PR + "Relationship"):
            rel_map[rel.get("Id", "")] = rel.get("Target", "")

        tables: list[TableData] = []
        sheets = workbook.find(M + "sheets")
        if sheets is None:
            return tables
        for sheet in sheets.findall(M + "sheet"):
            name = sheet.get("name", "Hoja")
            target = rel_map.get(sheet.get(R + "id", ""), "")
            if not target:
                continue
            if target.startswith("/"):
                sheet_path = target.lstrip("/")
            else:
                sheet_path = "xl/" + target.lstrip("/")
            sheet_path = str(Path(sheet_path))
            try:
                root = ET.fromstring(archive.read(sheet_path))
            except (KeyError, ET.ParseError):
                continue
            rows: list[list[Any]] = []
            sheet_data = root.find(M + "sheetData")
            if sheet_data is None:
                continue
            for row_element in sheet_data.findall(M + "row"):
                row_number = int(row_element.get("r", str(len(rows) + 1)))
                while len(rows) < row_number:
                    rows.append([])
                row_values: list[Any] = []
                for cell in row_element.findall(M + "c"):
                    index = xlsx_col_index(cell.get("r", ""))
                    if index <= 0 or index > 200:
                        continue
                    while len(row_values) < index:
                        row_values.append("")
                    cell_type = cell.get("t", "")
                    formula = cell.find(M + "f")
                    value_node = cell.find(M + "v")
                    inline = cell.find(M + "is")
                    value: Any = ""
                    if cell_type == "s" and value_node is not None:
                        try:
                            value = shared_strings[int(value_node.text or "0")]
                        except (ValueError, IndexError):
                            value = ""
                    elif cell_type == "inlineStr" and inline is not None:
                        value = "".join(node.text or "" for node in inline.iter(M + "t"))
                    elif cell_type == "str" and value_node is not None:
                        value = value_node.text or ""
                    elif cell_type == "b" and value_node is not None:
                        value = (value_node.text == "1")
                    elif value_node is not None:
                        raw = value_node.text or ""
                        number = parse_number(raw)
                        value = number if number is not None else raw
                    elif formula is not None:
                        value = ""
                    row_values[index - 1] = value
                rows[row_number - 1] = row_values
            tables.extend(detect_header_candidates(path, name, rows))
        return tables


def read_csv_tables(path: Path) -> list[TableData]:
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AtlasError("No se pudo determinar la codificación del CSV.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [list(row) for row in csv.reader(io.StringIO(text), dialect)]
    return detect_header_candidates(path, "CSV", rows)


def detect_header_candidates(path: Path, sheet_name: str, rows: list[list[Any]]) -> list[TableData]:
    candidates: list[TableData] = []
    for row_index, row in enumerate(rows[:30], start=1):
        normalized = [normalize_text(value) for value in row]
        serial_score = max((serial_header_score(header) for header in normalized), default=0)
        metric_hits = sum(
            1 for header in normalized
            if any(token in header for token in ("impresion", "equivalent", "duplex", "ambas caras", "atasco", "escaneo", "digital", "copias", "color"))
        )
        if serial_score >= 70 and metric_hits >= 1:
            width = max(len(row), max((len(item) for item in rows[row_index:]), default=0))
            headers = [str(value or "").strip() for value in row] + [""] * max(0, width - len(row))
            data_rows = []
            for item in rows[row_index:]:
                padded = list(item) + [""] * max(0, width - len(item))
                if any(str(value).strip() for value in padded):
                    data_rows.append(padded[:width])
            candidates.append(TableData(path, sheet_name, row_index, headers[:width], data_rows))
    return candidates


def read_report(path: Path, source_spec: str = "") -> TableData:
    path = Path(path)
    if not path.exists():
        raise AtlasError(f"No existe el reporte: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        candidates = read_csv_tables(path)
    elif suffix == ".xlsx":
        candidates = read_xlsx_tables(path)
    elif suffix == ".ods":
        candidates = read_ods_tables(path)
    else:
        raise AtlasError("El reporte debe ser CSV, XLSX u ODS.")
    if not candidates:
        raise AtlasError("No se encontró una fila de encabezados reconocible en el reporte.")

    def candidate_score(table: TableData) -> int:
        mapping = configure_source_mapping(table.headers, source_spec, allow_partial=True)
        mapped = len(mapping.fields)
        july_hits = sum(1 for header in table.headers if "julio" in normalize_text(header))
        return mapped * 100 + july_hits * 10 + min(len(table.rows), 100)

    best = max(candidates, key=candidate_score)
    configure_source_mapping(best.headers, source_spec, allow_partial=False)
    return best


def read_atlas_counter_database(path: Path) -> TableData:
    """Build a report-like table from readings plus the equipment directory.

    The database is opened read-only.  Atlas' own canonical counter history is
    the source; equipment without a reading is included with empty counters so
    its dependency can still complete the master location.  No database rows
    are created, updated or deleted by the inserter.
    """
    path = Path(path)
    if not path.exists():
        raise AtlasError(f"No existe la base de datos de Atlas: {path}")
    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = {
                str(row[0]) for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
            if "atlas_counter_readings" in tables:
                rows = connection.execute(
                    """
                    SELECT id, equipment_id, reading_date, serial_snapshot AS serial_number,
                           total_prints, letter_prints, duplex_sheets, jam_events
                    FROM atlas_counter_readings
                    WHERE trim(coalesce(serial_snapshot, '')) <> ''
                    ORDER BY CASE WHEN reading_date = '' THEN 1 ELSE 0 END,
                             reading_date DESC, id DESC
                    """
                ).fetchall()
            elif "counter_records" in tables:
                rows = connection.execute(
                    """
                    SELECT id, equipment_id, reading_date, serial_number, total_prints,
                           letter_prints, duplex_sheets, jam_events
                    FROM counter_records
                    WHERE trim(coalesce(serial_number, '')) <> ''
                    ORDER BY CASE WHEN reading_date = '' THEN 1 ELSE 0 END,
                             reading_date DESC, id DESC
                    """
                ).fetchall()
            else:
                raise AtlasError("La base seleccionada no contiene el histórico de contadores de Atlas.")

            equipment_details_by_id: dict[int, dict[str, str]] = {}
            equipment_details_by_serial: dict[str, dict[str, str]] = {}
            equipment_rows: list[sqlite3.Row] = []
            if {"atlas_equipment", "atlas_dependencies"}.issubset(tables):
                equipment_rows = connection.execute(
                    """
                    SELECT e.id, e.serial_number, e.ip_address,
                           d.name AS dependency_name, d.floor AS dependency_floor
                    FROM atlas_equipment e
                    JOIN atlas_dependencies d ON d.id = e.dependency_id
                    """
                ).fetchall()
                for equipment in equipment_rows:
                    details = {
                        "dependency": str(equipment["dependency_name"] or "").strip(),
                        "floor": str(equipment["dependency_floor"] or "").strip(),
                        "ip": str(equipment["ip_address"] or "").strip(),
                    }
                    equipment_details_by_id[int(equipment["id"])] = details
                    serial_key = normalize_serial(equipment["serial_number"])
                    if serial_key:
                        equipment_details_by_serial[serial_key] = details
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise AtlasError(f"No se pudo leer el histórico de contadores de Atlas: {exc}") from exc

    latest: dict[str, sqlite3.Row] = {}
    for row in rows:
        serial_key = normalize_serial(row["serial_number"])
        if serial_key and serial_key not in latest:
            latest[serial_key] = row
    if not latest and not equipment_rows:
        raise AtlasError("La base de datos de Atlas todavía no contiene lecturas de contadores.")

    headers = [
        "Número de serie", "Total de impresiones",
        "Total de impresiones equivalentes", "Hojas ambas caras",
        "Eventos de atasco", "Dependencia", "Fecha de toma del contador",
        "Piso", "Dirección IP",
    ]
    data_rows = []
    for row in latest.values():
        equipment_id = row["equipment_id"]
        details: dict[str, str] = {}
        if equipment_id is not None:
            details = equipment_details_by_id.get(int(equipment_id), {})
        if not details:
            details = equipment_details_by_serial.get(normalize_serial(row["serial_number"]), {})
        data_rows.append([
            row["serial_number"], row["total_prints"], row["letter_prints"],
            row["duplex_sheets"], row["jam_events"], details.get("dependency", ""),
            str(row["reading_date"] or "").strip(), details.get("floor", ""), details.get("ip", ""),
        ])
    # La dependencia pertenece al equipo, no al registro histórico. Incluir los
    # equipos que todavía no tienen contador permite completar P sin fabricar
    # ceros ni tratar una ausencia de lectura como un contador real.
    historical_serials = set(latest)
    for equipment in equipment_rows:
        serial = str(equipment["serial_number"] or "").strip()
        serial_key = normalize_serial(serial)
        if not serial_key or serial_key in historical_serials:
            continue
        data_rows.append([
            serial, None, None, None, None,
            str(equipment["dependency_name"] or "").strip(), "",
            str(equipment["dependency_floor"] or "").strip(),
            str(equipment["ip_address"] or "").strip(),
        ])
    return TableData(
        path, "Histórico de contadores de Atlas", 1, headers, data_rows,
        source_record_count=len(rows),
        source_unique_count=len({normalize_serial(row[0]) for row in data_rows if normalize_serial(row[0])}),
        metadata={"atlas_database_path": str(path.resolve())},
    )


def serial_header_score(header: str) -> int:
    header = normalize_text(header)
    if header in {"n de serie", "no de serie", "numero de serie", "n serie", "serie", "serial no", "serial number"}:
        return 120
    if "numero" in header and "serie" in header:
        return 110
    if "serial" in header:
        return 100
    if header.endswith("serie"):
        return 80
    return 0


def base_field_score(key: str, header: str) -> int:
    h = normalize_text(header)
    if not h:
        return 0
    has_july = "julio" in h
    historical = any(month in h for month in ("abril", "mayo", "junio"))
    calculated = "calcul" in h or "acumul" in h or "consumo" in h
    score = 0

    if key == "principal":
        # CodeCafe Atlas exporta un contador general en “Total de impresiones”.
        # Ese valor alimenta AK. “Impresiones tamaño oficio” se conserva solo
        # como alternativa cuando el reporte realmente no contiene el total.
        if h in {"total de impresiones", "total impresiones"}:
            score = 170
        elif "total de impresiones" in h and "equivalent" not in h:
            score = 160 if has_july else 150
        elif "total impresiones" in h and not historical:
            score = 145
        elif h in {"impresiones tamano oficio", "impresiones oficio", "oficio", "total"}:
            score = 100
    elif key == "equivalente":
        if "total de impresiones equivalent" in h and has_july:
            score = 135
        elif h in {"impresiones tamano carta", "impresiones carta", "carta", "equivalente", "equivalentes"}:
            score = 100
        elif "equivalent" in h and not historical:
            score = 85
    elif key == "duplex":
        if h in {"hojas ambas caras julio", "duplex julio", "doble cara julio"}:
            score = 130
        elif "ambas caras" in h or "duplex" in h or "doble cara" in h:
            score = 90
    elif key == "atascos":
        if "atasco" in h and has_july:
            score = 130
        elif "evento" in h and "atasco" in h:
            score = 100
        elif "atasco" in h or "jams" in h:
            score = 90
    elif key == "escaneos":
        if "total escaneos" in h or "total de escaneos" in h:
            score = 125
        elif "escaneo" in h and "digital" not in h:
            score = 100
    elif key == "copias":
        if h == "total de copias" or h == "copias":
            score = 125
        elif "total copias" in h:
            score = 100
    elif key == "color":
        if "impresiones a color" in h:
            score = 125
        elif h in {"color", "impresiones color"}:
            score = 100
    elif key == "digitalizaciones":
        if "total digitalizaciones" in h or "total de digitalizaciones" in h:
            score = 125
        elif "digitalizacion" in h or "digitalizaciones" in h:
            score = 100

    if historical:
        score -= 90
    if calculated:
        score -= 65
    return max(score, 0)


def detect_mapping(headers: list[str], allow_partial: bool = False) -> FieldMapping:
    serial_scores = [(serial_header_score(header), index) for index, header in enumerate(headers)]
    serial_score, serial_col = max(serial_scores, default=(0, -1))
    if serial_score < 70:
        raise AtlasError("El reporte no contiene una columna reconocible de número de serie.")

    fields: dict[str, int] = {}
    source_headers: dict[str, str] = {}

    # Primero se identifica el par principal de contadores. Esto permite resolver
    # encabezados repetidos como “Hojas ambas caras” por proximidad.
    anchor_candidates: dict[str, list[tuple[int, int]]] = {
        key: [] for key in ("principal", "equivalente") if key in TARGET_BY_KEY
    }
    for key in anchor_candidates:
        for index, header in enumerate(headers):
            score = base_field_score(key, header)
            if score:
                anchor_candidates[key].append((score, index))
        if anchor_candidates[key]:
            score, index = max(anchor_candidates[key], key=lambda item: (item[0], -item[1]))
            if score >= 60:
                fields[key] = index
                source_headers[key] = headers[index]

    anchor = max(fields.get("principal", -1), fields.get("equivalente", -1))
    used = set(fields.values()) | {serial_col}
    for key in (
        key for key in ("duplex", "atascos", "escaneos", "copias", "color", "digitalizaciones")
        if key in TARGET_BY_KEY
    ):
        candidates = []
        for index, header in enumerate(headers):
            if index in used:
                continue
            score = base_field_score(key, header)
            if score <= 0:
                continue
            if anchor >= 0:
                if index > anchor and index <= anchor + 10:
                    score += 45 - (index - anchor)
                elif index < anchor:
                    score -= 35
            candidates.append((score, index))
        if candidates:
            score, index = max(candidates, key=lambda item: (item[0], -item[1]))
            if score >= 60:
                fields[key] = index
                source_headers[key] = headers[index]
                used.add(index)

    if not fields and not allow_partial:
        raise AtlasError(
            f"No se reconoció ningún campo de contador compatible con {target_range_label()}."
        )
    unmapped = [key for key in TARGET_BY_KEY if key not in fields]
    return FieldMapping(serial_col, fields, source_headers, unmapped)


def configure_source_mapping(
    headers: list[str], source_spec: str = "", allow_partial: bool = False
) -> FieldMapping:
    """Detect or manually select source columns.

    Manual order: serial, impressions, equivalents, duplex, jams, scans,
    copies, color and digitizations. A dash omits an unavailable counter.
    """
    raw = str(source_spec or "").strip()
    if normalize_text(raw) in {"", "auto", "automatico"}:
        return detect_mapping(headers, allow_partial=allow_partial)
    parts = [part.strip().upper() for part in re.split(r"[,;]", raw)]
    if not 1 <= len(parts) <= len(FIELD_DEFINITIONS) + 1:
        raise AtlasError(
            "Indique primero la serie y, opcionalmente, las columnas de contador que existan."
        )
    serial_col = column_number(parts[0]) - 1
    if serial_col >= len(headers):
        raise AtlasError(f"La columna fuente {parts[0]} no existe en la tabla detectada.")
    if len(parts) == 1:
        detected = detect_mapping(headers, allow_partial=allow_partial)
        if serial_col in detected.fields.values():
            raise AtlasError(
                f"La columna fuente {parts[0]} no puede usarse simultáneamente como serie y contador."
            )
        return FieldMapping(
            serial_col,
            detected.fields,
            detected.source_headers,
            detected.unmapped,
        )
    fields: dict[str, int] = {}
    source_headers: dict[str, str] = {}
    used = {serial_col}
    for (key, _), token in zip(FIELD_DEFINITIONS, parts[1:]):
        if key not in TARGET_BY_KEY or token in {"", "-", "—", "NO", "N/A"}:
            continue
        index = column_number(token) - 1
        if index >= len(headers):
            raise AtlasError(f"La columna fuente {token} no existe en la tabla detectada.")
        if index in used:
            raise AtlasError(f"La columna fuente {token} fue asignada más de una vez.")
        used.add(index)
        fields[key] = index
        source_headers[key] = headers[index] or f"Columna {token}"
    if not fields and not allow_partial:
        raise AtlasError("Seleccione al menos una columna de contador en la fuente.")
    return FieldMapping(serial_col, fields, source_headers, [key for key in TARGET_BY_KEY if key not in fields])


def locality_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h == "localidad":
        return 120
    if "localidad" in h:
        return 105
    if h in {"ciudad", "municipio"}:
        return 35
    return 0


def status_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h in {"estatus", "status", "estado del equipo", "estatus del equipo"}:
        return 120
    if "estatus" in h and "equipo" in h:
        return 110
    return 0


def equipment_location_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h in {"ubicacion de equipo", "ubicacion del equipo", "ubicacion equipo"}:
        return 140
    if "ubicacion" in h and "equipo" in h:
        return 125
    return 0


def counter_date_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h in {"fecha de toma del contador", "fecha del contador", "fecha de lectura"}:
        return 150
    if "fecha" in h and ("contador" in h or "lectura" in h):
        return 120
    return 0


def floor_header_score(header: Any) -> int:
    h = normalize_text(header)
    return 150 if h == "piso" else 0


def ip_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h in {"direccion ip", "ip", "ip del equipo", "direccion ip del equipo"}:
        return 150
    if "direccion" in h and "ip" in h:
        return 120
    return 0


def dependency_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h in {"dependencia", "dependency", "dependencia del equipo"}:
        return 140
    if "dependencia" in h:
        return 110
    return 0


def source_dependency_column(headers: list[str]) -> Optional[int]:
    candidates = [
        (dependency_header_score(header), index)
        for index, header in enumerate(headers)
        if dependency_header_score(header)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], -item[1]))[1]


def source_auxiliary_column(headers: list[str], scorer) -> Optional[int]:
    candidates = [(scorer(header), index) for index, header in enumerate(headers) if scorer(header)]
    return max(candidates, key=lambda item: (item[0], -item[1]))[1] if candidates else None


def _master_header_preview(document: ODSDocument | XLSXDocument, sheet: ET.Element, rows: int = 4) -> str:
    preview: list[str] = []
    for row_number in range(1, rows + 1):
        row = document.get_row(sheet, row_number)
        populated = []
        for col in range(1, min(TARGET_LAST_COL, 16) + 1):
            value = str(document.cell_value(document.get_cell(row, col)) or "").strip()
            if value:
                populated.append(f"{col_letter(col)}{row_number}={value!r}")
        if populated:
            preview.append("; ".join(populated[:8]))
    return " | ".join(preview)


def _master_data_rows(
    document: ODSDocument | XLSXDocument,
    sheet: ET.Element,
    header_row: int,
    serial_col: int,
) -> list[int]:
    """Return actual data rows without assuming a fixed institutional range."""
    populated: list[int] = []
    if isinstance(document, ODSDocument):
        for row_number, values in iter_ods_rows(sheet, max_rows=50000, max_cols=max(serial_col, TARGET_LAST_COL, 20)):
            if row_number <= header_row:
                continue
            value = values[serial_col - 1] if serial_col <= len(values) else ""
            if normalize_serial(value):
                populated.append(row_number)
    else:
        for row in document._sheet_data(sheet).findall(XM + "row"):
            row_number = int(row.get("r", "0") or 0)
            if row_number <= header_row:
                continue
            if normalize_serial(document.cell_value(document.get_cell(row, serial_col))):
                populated.append(row_number)
    return populated


def detect_master_layout(
    document: ODSDocument | XLSXDocument,
    sheet: ET.Element,
    serial_spec: str = "",
) -> MasterLayout:
    """Detecta la disposición real del maestro sin asumir que Serie está en E.

    La hoja oficial descargada como XLSX puede conservar una disposición donde
    E=Modelo y F=N.° de Serie, mientras que la copia ODS usada inicialmente tiene
    E=N.° de Serie y F=Modelo. AK:AR permanecen como el bloque autorizado.
    """
    explicit_serial_col = None
    if normalize_text(serial_spec) not in {"", "auto", "automatico"}:
        explicit_serial_col = column_number(serial_spec)
    candidates: list[tuple[int, ...]] = []
    for row_number in range(1, MASTER_HEADER_SCAN_ROWS + 1):
        row = document.get_row(sheet, row_number)
        serial_candidates: list[tuple[int, int]] = []
        locality_candidates: list[tuple[int, int]] = []
        status_candidates: list[tuple[int, int]] = []
        equipment_location_candidates: list[tuple[int, int]] = []
        counter_date_candidates: list[tuple[int, int]] = []
        floor_candidates: list[tuple[int, int]] = []
        ip_candidates: list[tuple[int, int]] = []
        for col in range(1, max(TARGET_LAST_COL, explicit_serial_col or 0) + 1):
            value = document.cell_value(document.get_cell(row, col))
            if explicit_serial_col is None:
                serial_score = serial_header_score(normalize_text(value))
                if serial_score:
                    serial_candidates.append((serial_score, col))
            locality_score = locality_header_score(value)
            if locality_score:
                locality_candidates.append((locality_score, col))
            status_score = status_header_score(value)
            if status_score:
                status_candidates.append((status_score, col))
            location_score = equipment_location_header_score(value)
            if location_score:
                equipment_location_candidates.append((location_score, col))
            for scorer, target in (
                (counter_date_header_score, counter_date_candidates),
                (floor_header_score, floor_candidates),
                (ip_header_score, ip_candidates),
            ):
                auxiliary_score = scorer(value)
                if auxiliary_score:
                    target.append((auxiliary_score, col))
        if explicit_serial_col is not None:
            serial_candidates.append((200, explicit_serial_col))
        if not serial_candidates or not locality_candidates:
            continue
        serial_score, serial_col = max(serial_candidates, key=lambda item: (item[0], -item[1]))
        locality_score, locality_col = max(locality_candidates, key=lambda item: (item[0], -item[1]))
        if serial_col == locality_col:
            continue
        # Favorece una fila compacta y la localidad en el bloque administrativo.
        score = serial_score + locality_score - abs(locality_col - serial_col)
        status_col = max(status_candidates, default=(0, 0), key=lambda item: (item[0], -item[1]))[1]
        equipment_location_col = max(
            equipment_location_candidates,
            default=(0, 0),
            key=lambda item: (item[0], -item[1]),
        )[1]
        auxiliary_cols = [
            max(items, default=(0, 0), key=lambda item: (item[0], -item[1]))[1]
            for items in (counter_date_candidates, floor_candidates, ip_candidates)
        ]
        candidates.append((score, -row_number, serial_col, locality_col, status_col, equipment_location_col, *auxiliary_cols))

    if candidates:
        (_, negative_row, serial_col, locality_col, status_col, equipment_location_col,
         counter_date_col, floor_col, ip_col) = max(candidates)
        header_row = -negative_row
    else:
        preview = _master_header_preview(document, sheet)
        raise AtlasError(
            "No se localizaron automáticamente los encabezados de N.° de Serie y LOCALIDAD "
            f"en las primeras {MASTER_HEADER_SCAN_ROWS} filas. No se realizará ninguna escritura. "
            + (f"Contenido observado: {preview}" if preview else "")
        )

    data_rows = _master_data_rows(document, sheet, header_row, serial_col)
    if not data_rows:
        raise AtlasError(
            f"La columna detectada para número de serie ({col_letter(serial_col)}) no contiene equipos "
            f"después de la fila de encabezados {header_row}. No se realizará ninguna escritura."
        )
    first_row, last_row = min(data_rows), max(data_rows)

    # Confirmación estructural con registros reales dentro del rango detectado.
    torreon_records = 0
    nonempty_serials = 0
    target_evidence = 0
    for row_number in data_rows:
        row = document.get_row(sheet, row_number)
        serial_raw = document.cell_value(document.get_cell(row, serial_col))
        locality = document.cell_value(document.get_cell(row, locality_col))
        if normalize_serial(serial_raw):
            nonempty_serials += 1
        if normalize_text(locality) == normalize_text(TARGET_LOCALITY) and normalize_serial(serial_raw):
            torreon_records += 1
            for col in range(TARGET_FIRST_COL, TARGET_LAST_COL + 1):
                cell = document.get_cell(row, col)
                if document.cell_formula(cell) or parse_number(document.cell_value(cell)) is not None:
                    target_evidence += 1

    if torreon_records == 0:
        raise AtlasError(
            f"No se encontraron equipos de Torreón usando Serie={col_letter(serial_col)} y "
            f"LOCALIDAD={col_letter(locality_col)} entre las filas {first_row}–{last_row}. "
            "No se realizará ninguna escritura."
        )

    # Los encabezados de AK:AR pueden estar distribuidos en varias filas o celdas
    # combinadas en el XLSX. Se usan como evidencia adicional, no como requisito rígido.
    target_header_hits = 0
    token_groups = (
        ("impresion", "carta"),
        ("impresion", "equivalent", "oficio"),
        ("ambas caras", "duplex"),
        ("atasco",),
        ("escaneo",),
        ("copias",),
        ("color",),
        ("digital",),
    )
    target_tokens = {
        col: tokens for (_, col, _, _), tokens in zip(TARGETS, token_groups)
    }
    for col, tokens in target_tokens.items():
        combined = " ".join(
            normalize_text(document.cell_value(document.get_cell(document.get_row(sheet, row_number), col)))
            for row_number in range(1, MASTER_HEADER_SCAN_ROWS + 1)
        )
        if any(token in combined for token in tokens):
            target_header_hits += 1

    validation_mode = (
        f"encabezados detectados; {target_header_hits}/8 campos {target_range_label()} reconocidos"
        if target_header_hits
        else f"encabezados de {target_range_label()} distribuidos o vacíos; bloque confirmado por {target_evidence} celdas existentes"
    )
    return MasterLayout(
        header_row, serial_col, locality_col, first_row, last_row,
        validation_mode, status_col, equipment_location_col,
        counter_date_col, floor_col, ip_col,
    )


def validate_master_layout(
    document: ODSDocument | XLSXDocument,
    sheet: ET.Element,
    expected: Optional[MasterLayout] = None,
    serial_spec: str = "",
) -> MasterLayout:
    layout = detect_master_layout(document, sheet, serial_spec)
    if expected is not None and (
        layout.serial_col != expected.serial_col
        or layout.locality_col != expected.locality_col
        or layout.first_row != expected.first_row
        or layout.last_row != expected.last_row
        or layout.status_col != expected.status_col
        or layout.equipment_location_col != expected.equipment_location_col
        or layout.counter_date_col != expected.counter_date_col
        or layout.floor_col != expected.floor_col
        or layout.ip_col != expected.ip_col
    ):
        raise AtlasError(
            "La disposición de la hoja maestra cambió desde el análisis. "
            f"Antes: Serie={col_letter(expected.serial_col)}, LOCALIDAD={col_letter(expected.locality_col)}; "
            f"ahora: Serie={col_letter(layout.serial_col)}, LOCALIDAD={col_letter(layout.locality_col)}. "
            "Se canceló la escritura."
        )
    return layout


def load_master_records(
    document: ODSDocument | XLSXDocument,
    sheet: ET.Element,
    layout: MasterLayout,
) -> tuple[dict[str, MasterRecord], set[str]]:
    records_by_serial: dict[str, list[MasterRecord]] = defaultdict(list)
    for row_number in range(layout.first_row, layout.last_row + 1):
        row = document.get_row(sheet, row_number)
        serial_raw = str(document.cell_value(document.get_cell(row, layout.serial_col)) or "").strip()
        locality = str(document.cell_value(document.get_cell(row, layout.locality_col)) or "").strip()
        if normalize_text(locality) != normalize_text(TARGET_LOCALITY):
            continue
        serial_key = normalize_serial(serial_raw)
        if not serial_key:
            continue
        current_values: dict[str, Any] = {}
        formula_fields: set[str] = set()
        for letter, col, _, key in TARGETS:
            cell = document.get_cell(row, col)
            current_values[key] = document.cell_value(cell)
            if document.cell_formula(cell):
                formula_fields.add(key)
        if layout.status_col:
            status_cell = document.get_cell(row, layout.status_col)
            current_status = document.cell_value(status_cell)
            status_has_formula = bool(document.cell_formula(status_cell))
        else:
            current_status = ""
            status_has_formula = False
        if layout.equipment_location_col:
            location_cell = document.get_cell(row, layout.equipment_location_col)
            current_location = document.cell_value(location_cell)
            location_has_formula = bool(document.cell_formula(location_cell))
        else:
            current_location = ""
            location_has_formula = False
        auxiliary_values: list[tuple[Any, bool]] = []
        for auxiliary_col in (layout.counter_date_col, layout.floor_col, layout.ip_col):
            if auxiliary_col:
                auxiliary_cell = document.get_cell(row, auxiliary_col)
                auxiliary_values.append((
                    document.cell_value(auxiliary_cell),
                    bool(document.cell_formula(auxiliary_cell)),
                ))
            else:
                auxiliary_values.append(("", False))
        records_by_serial[serial_key].append(
            MasterRecord(
                row_number,
                serial_raw,
                serial_key,
                locality,
                current_values,
                formula_fields,
                current_status,
                status_has_formula,
                current_location,
                location_has_formula,
                auxiliary_values[0][0], auxiliary_values[0][1],
                auxiliary_values[1][0], auxiliary_values[1][1],
                auxiliary_values[2][0], auxiliary_values[2][1],
            )
        )
    duplicates = {serial for serial, records in records_by_serial.items() if len(records) > 1}
    unique = {serial: records[0] for serial, records in records_by_serial.items() if len(records) == 1}
    return unique, duplicates


def _effective_counter_value(item: FieldDecision) -> Any:
    """Valor que permanecerá en la copia después de aplicar la decisión."""
    if item.action in {"escribir", "sobrescribir", "escribir_cero", "igual"}:
        return item.source_value
    return item.existing_value


def _equipment_location_decision(
    record: MasterRecord,
    source_location: str,
    location_col: int,
    location_mode: str,
) -> tuple[str, str]:
    source_location = str(source_location or "").strip()
    mode = normalize_text(location_mode)
    if mode not in {"fill", "replace", "completar", "reemplazar"}:
        return "conservar", source_location
    if not location_col:
        return "columna_no_detectada", source_location
    if not source_location:
        return "sin_dependencia", ""
    if record.location_has_formula:
        return "formula", source_location
    existing = str(record.current_location or "").strip()
    if not existing:
        return "escribir", source_location
    # En modo reemplazo la base de Atlas es canónica: diferencias de acentos,
    # abreviaturas, mayúsculas o redacción también deben corregirse. Solo una
    # coincidencia textual exacta (ignorando espacios exteriores) se conserva.
    if existing == source_location:
        return "igual", source_location
    if mode in {"replace", "reemplazar"}:
        return "sobrescribir", source_location
    return "conservar", source_location


def normalize_counter_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return raw


def normalize_ip(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return ""


def _fill_auxiliary_decision(existing: Any, has_formula: bool, source: Any, column: int) -> tuple[str, str]:
    value = str(source or "").strip()
    if not column:
        return "columna_no_detectada", value
    if not value:
        return "sin_dato", ""
    if has_formula:
        return "formula", value
    current = str(existing or "").strip()
    if not current:
        return "escribir", value
    if normalize_text(current) == normalize_text(value):
        return "igual", value
    return "conservar", value


def _operation_status_decision(
    record: MasterRecord,
    fields: list[FieldDecision],
) -> tuple[str, bool, str]:
    """Determina la acción derivada sobre H sin alterar equipos no elegibles."""
    has_positive_counter = any(
        (number := parse_number(_effective_counter_value(item))) is not None and float(number) > 0
        for item in fields
    )
    if not has_positive_counter:
        return "conservar", False, "H queda sin cambios: no hay contadores mayores a 0."
    if record.status_has_formula:
        return "formula", True, "H contiene una fórmula y permanece protegida."
    if str(record.current_status or "").strip() == STATUS_VALUE:
        return "igual", True, f'H ya contiene "{STATUS_VALUE}".'
    return "escribir", True, f'H se actualizará a "{STATUS_VALUE}".'


def analyze_files(
    master_path: Path,
    report_path: Path,
    overwrite_existing: bool = False,
    master_sheet_name: str = "",
    target_spec: str = "",
    source_spec: str = "",
    master_serial_spec: str = "",
    report_table: Optional[TableData] = None,
    create_missing_rows: bool = False,
    allow_similar_missing_rows: bool = False,
    serial_overrides: Optional[dict[str, str]] = None,
    location_mode: str = "off",
    auxiliary_mode: str = "off",
    import_missing_ips: bool = False,
) -> AnalysisResult:
    master_path = Path(master_path)
    report_path = Path(report_path)
    document = open_master_document(master_path)
    sheet = document.find_sheet((master_sheet_name,)) if master_sheet_name.strip() else document.find_sheet()
    master_sheet_name = document.sheet_name(sheet)
    master_layout = validate_master_layout(document, sheet, serial_spec=master_serial_spec)
    normalized_location_mode = normalize_text(location_mode)
    normalized_auxiliary_mode = normalize_text(auxiliary_mode)
    if normalized_location_mode not in {"", "off", "fill", "replace", "completar", "reemplazar"}:
        raise AtlasError("El modo de actualización de ubicación no es válido.")
    if normalized_location_mode not in {"", "off"} and not master_layout.equipment_location_col:
        raise AtlasError(
            "Se solicitó actualizar la ubicación, pero no se encontró el encabezado "
            "‘Ubicación de Equipo’ en la hoja maestra."
        )
    if normalized_auxiliary_mode not in {"", "off", "fill", "completar"}:
        raise AtlasError("El modo de actualización de fecha, piso e IP no es válido.")
    if normalized_auxiliary_mode not in {"", "off"}:
        missing = [
            label for label, col in (
                ("Fecha de toma del contador", master_layout.counter_date_col),
                ("Piso", master_layout.floor_col),
                ("Dirección IP", master_layout.ip_col),
            ) if not col
        ]
        if missing:
            raise AtlasError("No se encontraron estos encabezados en la hoja maestra: " + ", ".join(missing))
    if normalize_text(target_spec) in {"", "auto", "automatico"}:
        configure_targets_from_master(
            document,
            sheet,
            master_layout.header_row,
            excluded_cols={col for col in (
                master_layout.equipment_location_col if normalized_location_mode not in {"", "off"} else 0,
                master_layout.counter_date_col if normalized_auxiliary_mode not in {"", "off"} else 0,
                master_layout.floor_col if normalized_auxiliary_mode not in {"", "off"} else 0,
                master_layout.ip_col if normalized_auxiliary_mode not in {"", "off"} else 0,
            ) if col},
        )
    else:
        if (
            normalized_location_mode not in {"", "off"}
            and master_layout.equipment_location_col
        ):
            configure_targets_without_reserved_location(
                target_spec,
                master_layout.equipment_location_col,
            )
        else:
            configure_target_columns(target_spec)
    master_layout = validate_master_layout(document, sheet, serial_spec=master_serial_spec)
    master_records, master_duplicates = load_master_records(document, sheet, master_layout)

    report = report_table if report_table is not None else read_report(report_path, source_spec)
    mapping = configure_source_mapping(report.headers, source_spec)
    report = apply_serial_overrides(report, mapping, serial_overrides)
    dependency_col = source_dependency_column(report.headers)
    source_date_col = source_auxiliary_column(report.headers, counter_date_header_score)
    source_floor_col = source_auxiliary_column(report.headers, floor_header_score)
    source_ip_col = source_auxiliary_column(report.headers, ip_header_score)
    atlas_database_path = Path(report.metadata["atlas_database_path"]) if report.metadata.get("atlas_database_path") else None

    report_serial_counter: Counter[str] = Counter()
    report_rows_prepared = []
    for offset, row in enumerate(report.rows, start=report.header_row + 1):
        serial_raw = row[mapping.serial_col] if mapping.serial_col < len(row) else ""
        serial_key = normalize_serial(serial_raw)
        if not serial_key:
            if any(not is_blank_value(value) for value in row):
                report_rows_prepared.append((offset, str(serial_raw).strip(), "", row))
            continue
        report_serial_counter[serial_key] += 1
        report_rows_prepared.append((offset, str(serial_raw).strip(), serial_key, row))
    report_duplicates = {serial for serial, count in report_serial_counter.items() if count > 1}

    decisions: list[MatchDecision] = []
    next_new_row = master_layout.last_row + 1
    for report_row, serial_raw, serial_key, row in report_rows_prepared:
        if not serial_key:
            decisions.append(MatchDecision(
                report_row, serial_raw, serial_key, None, "serie_vacia",
                "La fila contiene datos, pero no incluye un número de serie. No se realizó ninguna escritura."
            ))
            continue
        if serial_key in report_duplicates:
            decisions.append(MatchDecision(
                report_row, serial_raw, serial_key, None, "duplicado_reporte",
                "El número de serie aparece más de una vez en el reporte. No se escribió ninguna fila y se añadió al reporte de discrepancias."
            ))
            continue
        if serial_key in master_duplicates:
            decisions.append(MatchDecision(
                report_row, serial_raw, serial_key, None, "duplicado_maestro",
                "El número de serie aparece más de una vez en la hoja maestra de Torreón. No se eligió una fila y se añadió al reporte de discrepancias."
            ))
            continue

        row_has_numeric_counter = any(
            source_col < len(row) and parse_number(row[source_col]) is not None
            for source_col in mapping.fields.values()
        )
        record = master_records.get(serial_key)
        creates_master_row = False
        similar_warning: list[tuple[int, MasterRecord]] = []
        if record is None:
            if not create_missing_rows:
                decisions.append(MatchDecision(
                    report_row, serial_raw, serial_key, None, "no_encontrado",
                    f"No existe una coincidencia exacta del número de serie normalizado en Torreón, filas {master_layout.first_row}–{master_layout.last_row}. No se intentó ninguna corrección aproximada."
                ))
                continue
            if not row_has_numeric_counter:
                decisions.append(MatchDecision(
                    report_row, serial_raw, serial_key, None, "no_encontrado",
                    "El equipo existe en Atlas, pero no tiene una lectura de contadores y tampoco "
                    "existe en la hoja maestra. No se creó una fila nueva."
                ))
                continue
            similar_warning = similar_master_serials(serial_key, master_records)
            if similar_warning and not allow_similar_missing_rows:
                candidates = ", ".join(
                    f"{item.serial_raw} (fila {item.row_number}, distancia {distance})"
                    for distance, item in similar_warning
                )
                decisions.append(MatchDecision(
                    report_row, serial_raw, serial_key, None,
                    "posible_serie_mal_escrita",
                    "La serie no se añadirá automáticamente porque se parece a una ya existente: "
                    f"{candidates}. Confirme cuál escritura es correcta.",
                    matched_serial_raw=similar_warning[0][1].serial_raw,
                    approximate_match=True,
                ))
                continue
            creates_master_row = True
            record = MasterRecord(
                next_new_row, serial_raw, serial_key, TARGET_LOCALITY,
                {key: "" for _, _, _, key in TARGETS}, set(), "", False,
            )
            master_records[serial_key] = record
            next_new_row += 1

        source_location = (
            str(row[dependency_col] or "").strip()
            if dependency_col is not None and dependency_col < len(row)
            else ""
        )
        source_date = normalize_counter_date(row[source_date_col]) if source_date_col is not None and source_date_col < len(row) else ""
        source_floor = str(row[source_floor_col] or "").strip() if source_floor_col is not None and source_floor_col < len(row) else ""
        source_ip_raw = str(row[source_ip_col] or "").strip() if source_ip_col is not None and source_ip_col < len(row) else ""
        source_ip = normalize_ip(source_ip_raw)

        field_decisions_by_key: dict[str, FieldDecision] = {}
        compatible_counter_exists = False
        invalid_source_exists = False
        for key, source_col in mapping.fields.items():
            letter, _, target_label = TARGET_BY_KEY[key]
            source_header = mapping.source_headers[key]
            raw_source = row[source_col] if source_col < len(row) else ""
            parsed_source = parse_number(raw_source)
            existing = record.current_values.get(key)
            existing_has_content = not is_blank_value(existing)

            if parsed_source is None:
                if is_blank_value(raw_source):
                    action = "valor_maestro_invalido" if existing_has_content and parse_number(existing) is None else "sin_dato"
                    stored_source = None
                else:
                    action = "valor_invalido"
                    invalid_source_exists = True
                    stored_source = raw_source
            else:
                compatible_counter_exists = True
                stored_source = parsed_source
                if key in record.formula_fields:
                    action = "formula"
                elif existing_has_content and numeric_equal(existing, parsed_source):
                    action = "igual"
                elif existing_has_content and not overwrite_existing:
                    action = "conflicto"
                elif existing_has_content:
                    action = "sobrescribir"
                else:
                    action = "escribir"
            field_decisions_by_key[key] = FieldDecision(
                key, letter, target_label, source_header, stored_source, existing, action
            )

        # La regla no negociable: una vez confirmada la serie exacta y al menos un
        # contador válido, toda celda realmente vacía de AK–AR sin dato se llena con 0.
        for _, _, target_label, key in TARGETS:
            if key in field_decisions_by_key:
                item = field_decisions_by_key[key]
                if (
                    compatible_counter_exists
                    and item.action == "sin_dato"
                    and key not in record.formula_fields
                    and is_blank_value(item.existing_value)
                ):
                    item.source_value = 0
                    item.source_header += " (celda vacía; se completa con 0)"
                    item.action = "escribir_cero"
                continue

            letter, _, _ = TARGET_BY_KEY[key]
            existing = record.current_values.get(key)
            if key in record.formula_fields:
                action = "formula"
                source_value = None
                header = "Sin campo compatible; la celda maestra contiene fórmula"
            elif compatible_counter_exists and is_blank_value(existing):
                action = "escribir_cero"
                source_value = 0
                header = "Sin campo compatible en el reporte (celda vacía; se completa con 0)"
            elif not is_blank_value(existing) and parse_number(existing) is None:
                action = "valor_maestro_invalido"
                source_value = None
                header = "Sin campo compatible; la celda maestra contiene texto no numérico"
            else:
                action = "conservar" if not is_blank_value(existing) else "sin_dato"
                source_value = None
                header = "Sin campo compatible en el reporte"
            field_decisions_by_key[key] = FieldDecision(
                key, letter, target_label, header, source_value, existing, action
            )

        field_decisions = [field_decisions_by_key[key] for _, _, _, key in TARGETS]
        writable = sum(1 for item in field_decisions if item.action in {"escribir", "sobrescribir", "escribir_cero"})
        discrepancies = sum(1 for item in field_decisions if item.action in {
            "conflicto", "formula", "valor_invalido", "valor_maestro_invalido", "sobrescribir"
        })
        has_positive_counter = any(
            (number := parse_number(_effective_counter_value(item))) is not None and float(number) > 0
            for item in field_decisions
        )

        if not compatible_counter_exists:
            status = "sin_datos_validos"
            details = "La serie coincide exactamente, pero el reporte no contiene ningún contador numérico válido. Revisión manual requerida."
        elif creates_master_row:
            if similar_warning:
                candidates = ", ".join(
                    f"{item.serial_raw} (fila {item.row_number})"
                    for _, item in similar_warning
                )
                status = "nueva_fila_con_advertencia"
                details = (
                    f"Alta autorizada después de advertir una serie parecida: {candidates}. "
                    f"Se creará la fila {record.row_number} con Serie, LOCALIDAD={TARGET_LOCALITY} "
                    f"y {writable} contador(es)."
                )
            else:
                status = "nueva_fila"
                details = (
                    f"La serie no existe en la hoja maestra. Se creará la fila {record.row_number} "
                    f"con Serie, LOCALIDAD={TARGET_LOCALITY} y {writable} contador(es)."
                )
        elif writable:
            status = "listo_con_discrepancias" if discrepancies else "listo"
            details = f"Coincidencia exacta. {writable} celda(s) de {target_range_label()} lista(s) para escribir."
            if discrepancies:
                details += f" {discrepancies} discrepancia(s) se documentarán en el CSV adicional."
        elif discrepancies:
            status = "discrepancia"
            details = f"Coincidencia exacta, pero {discrepancies} discrepancia(s) impiden escrituras automáticas en las celdas afectadas."
        else:
            status = "sin_cambios"
            details = "La serie coincide exactamente y los valores ya son iguales o no requieren cambios."

        if master_layout.status_col:
            operation_action, has_positive_counter, operation_detail = _operation_status_decision(
                record, field_decisions
            )
            details += f" Estado {col_letter(master_layout.status_col)}: {operation_detail}"
        else:
            operation_action = "conservar"

        location_action, location_value = _equipment_location_decision(
            record,
            source_location,
            master_layout.equipment_location_col,
            normalized_location_mode,
        )
        if normalized_auxiliary_mode not in {"", "off"}:
            date_action, date_value = _fill_auxiliary_decision(
                record.current_counter_date, record.counter_date_has_formula,
                source_date, master_layout.counter_date_col,
            )
            floor_action, floor_value = _fill_auxiliary_decision(
                record.current_floor, record.floor_has_formula,
                source_floor, master_layout.floor_col,
            )
            existing_ip = normalize_ip(record.current_ip)
            if source_ip and existing_ip and source_ip != existing_ip:
                ip_action, ip_value = "conflicto", source_ip
            else:
                ip_action, ip_value = _fill_auxiliary_decision(
                    record.current_ip, record.ip_has_formula,
                    source_ip, master_layout.ip_col,
                )
        else:
            date_action = floor_action = ip_action = "conservar"
            date_value = floor_value = ip_value = ""

        atlas_ip_action = "conservar"
        atlas_ip_value = ""
        if import_missing_ips and atlas_database_path and not source_ip:
            master_ip = normalize_ip(record.current_ip)
            if master_ip:
                atlas_ip_action, atlas_ip_value = "importar", master_ip
        if normalized_location_mode not in {"", "off"}:
            location_letter = col_letter(master_layout.equipment_location_col)
            if location_action == "escribir":
                details += f" Ubicación {location_letter}: se completará con ‘{location_value}’."
            elif location_action == "sobrescribir":
                details += (
                    f" Ubicación {location_letter}: ‘{record.current_location}’ se reemplazará "
                    f"por ‘{location_value}’."
                )
            elif location_action == "igual":
                details += f" Ubicación {location_letter}: ya coincide con ‘{location_value}’."
            elif location_action == "sin_dependencia":
                details += " Ubicación: la base de Atlas no contiene una dependencia para esta serie."
            elif location_action == "formula":
                details += f" Ubicación {location_letter}: contiene una fórmula y permanece protegida."
            elif location_action == "conservar":
                details += f" Ubicación {location_letter}: se conserva el valor existente."

        if not compatible_counter_exists:
            if location_action in {"escribir", "sobrescribir"}:
                status = "ubicacion_lista"
                details = (
                    "El equipo no tiene una lectura de contadores, pero su dependencia está "
                    "registrada en Atlas y la ubicación sí se actualizará. " + details
                )
            elif location_action in {"igual", "conservar"}:
                status = "sin_cambios"

        decisions.append(MatchDecision(
            report_row, serial_raw, serial_key, record.row_number, status, details, field_decisions,
            matched_serial_raw=(similar_warning[0][1].serial_raw if similar_warning else record.serial_raw),
            approximate_match=bool(similar_warning),
            operation_status_action=operation_action,
            operation_status_existing=record.current_status,
            has_positive_counter=has_positive_counter,
            creates_master_row=creates_master_row and compatible_counter_exists,
            location_action=location_action,
            location_existing=record.current_location,
            location_value=location_value,
            counter_date_action=date_action,
            counter_date_existing=record.current_counter_date,
            counter_date_value=date_value,
            floor_action=floor_action,
            floor_existing=record.current_floor,
            floor_value=floor_value,
            ip_action=ip_action,
            ip_existing=record.current_ip,
            ip_value=ip_value,
            atlas_ip_action=atlas_ip_action,
            atlas_ip_existing=source_ip_raw,
            atlas_ip_value=atlas_ip_value,
        ))

    return AnalysisResult(
        master_path=master_path,
        report_path=report_path,
        master_sheet=master_sheet_name,
        master_layout=master_layout,
        report_sheet=report.sheet_name,
        report_header_row=report.header_row,
        mapping=mapping,
        overwrite_existing=overwrite_existing,
        decisions=decisions,
        master_records=master_records,
        report_duplicate_serials=report_duplicates,
        master_duplicate_serials=master_duplicates,
        source_record_count=report.source_record_count,
        source_unique_count=report.source_unique_count,
        location_mode=normalized_location_mode or "off",
        auxiliary_mode=normalized_auxiliary_mode or "off",
        import_missing_ips=import_missing_ips,
        atlas_database_path=atlas_database_path,
    )



def analyze_multiple_files(
    master_path: Path,
    report_paths: list[Path],
    overwrite_existing: bool = False,
    master_sheet_name: str = "",
    target_spec: str = "",
    source_spec: str = "",
    master_serial_spec: str = "",
    report_tables: Optional[list[TableData]] = None,
    create_missing_rows: bool = False,
    allow_similar_missing_rows: bool = False,
    serial_overrides: Optional[dict[str, str]] = None,
    location_mode: str = "off",
    auxiliary_mode: str = "off",
    import_missing_ips: bool = False,
) -> AnalysisResult:
    """Consolida varias fuentes usando exclusivamente la serie exacta normalizada."""
    paths = [Path(path) for path in report_paths]
    tables = list(report_tables or [])
    sources: list[tuple[Path, Optional[TableData]]] = [(path, None) for path in paths]
    sources.extend((table.source_path, table) for table in tables)
    if not sources:
        raise AtlasError("Seleccione al menos un reporte fuente.")
    if len(sources) == 1:
        source_path, source_table = sources[0]
        result = analyze_files(
            master_path, source_path, overwrite_existing, master_sheet_name,
            target_spec, source_spec, master_serial_spec, source_table,
            create_missing_rows, allow_similar_missing_rows, serial_overrides,
            location_mode,
            auxiliary_mode, import_missing_ips,
        )
        for decision in result.decisions:
            decision.source_names = source_path.name
            for item in decision.fields:
                item.source_header = f"[{source_path.name}] {item.source_header}"
        return result

    analyses = [
        analyze_files(
            master_path, path, overwrite_existing, master_sheet_name,
            target_spec, source_spec, master_serial_spec, table, False, False,
            serial_overrides, location_mode, auxiliary_mode, import_missing_ips,
        )
        for path, table in sources
    ]
    paths = [path for path, _ in sources]
    base = analyses[0]
    grouped: dict[str, list[tuple[Path, MatchDecision]]] = defaultdict(list)
    order: list[str] = []
    for path, analysis in zip(paths, analyses):
        for decision in analysis.decisions:
            group_key = decision.serial_key or f"{path}:{decision.report_row}:{decision.serial_raw}"
            if group_key not in grouped:
                order.append(group_key)
            grouped[group_key].append((path, decision))

    consolidated: list[MatchDecision] = []
    for group_key in order:
        entries = grouped[group_key]
        source_names = ", ".join(dict.fromkeys(path.name for path, _ in entries))
        matched = [(path, decision) for path, decision in entries if decision.master_row is not None]
        if not matched:
            for path, decision in entries:
                decision.source_names = path.name
                decision.details = f"Fuente: {path.name}. {decision.details}"
                consolidated.append(decision)
            continue

        for unmatched_path, unmatched_decision in entries:
            if unmatched_decision.master_row is None:
                unmatched_decision.source_names = unmatched_path.name
                unmatched_decision.details = f"Fuente: {unmatched_path.name}. {unmatched_decision.details}"
                consolidated.append(unmatched_decision)

        first_path, first = matched[0]
        record = base.master_records.get(first.serial_key)
        if record is None:
            first.source_names = source_names
            consolidated.append(first)
            continue

        field_results: list[FieldDecision] = []
        any_real_counter = False
        for _, _, target_label, field_key in TARGETS:
            letter, _, _ = TARGET_BY_KEY[field_key]
            existing = record.current_values.get(field_key)
            candidates: list[tuple[str, str, Any]] = []
            invalid_candidates: list[tuple[str, str, Any]] = []
            for path, decision in matched:
                item = next((candidate for candidate in decision.fields if candidate.key == field_key), None)
                if item is None:
                    continue
                if item.action == "valor_invalido":
                    invalid_candidates.append((path.name, item.source_header, item.source_value))
                    continue
                generated_zero = item.action == "escribir_cero"
                if item.source_value is not None and not generated_zero:
                    parsed = parse_number(item.source_value)
                    if parsed is not None:
                        candidates.append((path.name, item.source_header, parsed))
                        any_real_counter = True

            unique_values: list[Any] = []
            for _, _, value in candidates:
                if not any(numeric_equal(value, current) for current in unique_values):
                    unique_values.append(value)

            if field_key in record.formula_fields:
                action, value = "formula", None
                header = "Protegido por fórmula en la hoja maestra"
            elif invalid_candidates:
                action = "valor_invalido"
                value = "; ".join(str(raw) for _, _, raw in invalid_candidates)
                header = "; ".join(f"[{name}] {hdr} = {raw}" for name, hdr, raw in invalid_candidates)
            elif len(unique_values) > 1:
                action, value = "conflicto_fuentes", None
                header = "; ".join(f"[{name}] {hdr} = {display_number(val)}" for name, hdr, val in candidates)
            elif len(unique_values) == 1:
                value = unique_values[0]
                header = "; ".join(f"[{name}] {hdr}" for name, hdr, _ in candidates)
                if not is_blank_value(existing) and numeric_equal(existing, value):
                    action = "igual"
                elif not is_blank_value(existing) and not overwrite_existing:
                    action = "conflicto"
                elif not is_blank_value(existing):
                    action = "sobrescribir"
                else:
                    action = "escribir"
            elif not is_blank_value(existing) and parse_number(existing) is None:
                action, value = "valor_maestro_invalido", None
                header = "La celda maestra contiene texto no numérico"
            else:
                action, value = ("conservar", None) if not is_blank_value(existing) else ("sin_dato", None)
                header = "Sin campo compatible en las fuentes seleccionadas"

            field_results.append(FieldDecision(field_key, letter, target_label, header, value, existing, action))

        # Aun cuando otra celda tenga discrepancia, las celdas verdaderamente vacías
        # sin dato se completan con 0 si existe al menos un contador válido para la serie.
        if any_real_counter:
            for item in field_results:
                if item.action == "sin_dato" and item.key not in record.formula_fields and is_blank_value(item.existing_value):
                    item.source_value = 0
                    item.source_header += " (celda vacía; se completa con 0)"
                    item.action = "escribir_cero"

        writable = sum(1 for item in field_results if item.action in {"escribir", "sobrescribir", "escribir_cero"})
        discrepancies = sum(1 for item in field_results if item.action in {
            "conflicto", "conflicto_fuentes", "formula", "valor_invalido", "valor_maestro_invalido", "sobrescribir"
        })
        has_positive_counter = any(
            (number := parse_number(_effective_counter_value(item))) is not None and float(number) > 0
            for item in field_results
        )
        if not any_real_counter:
            status = "sin_datos_validos"
            details = "Las fuentes no contienen contadores numéricos válidos para esta serie exacta."
        elif writable:
            status = "listo_con_discrepancias" if discrepancies else "listo"
            details = f"Coincidencia exacta. {writable} celda(s) consolidadas listas para escribir."
            if discrepancies:
                details += f" {discrepancies} discrepancia(s) se documentarán en el CSV adicional."
        elif discrepancies:
            status = "discrepancia"
            details = f"{discrepancies} discrepancia(s) requieren revisión manual."
        else:
            status = "sin_cambios"
            details = "Los valores consolidados ya son iguales o no requieren cambios."

        if base.master_layout.status_col:
            operation_action, has_positive_counter, operation_detail = _operation_status_decision(
                record, field_results
            )
            details += f" Estado {col_letter(base.master_layout.status_col)}: {operation_detail}"
        else:
            operation_action = "conservar"

        location_values: list[str] = []
        for _, decision in matched:
            value = str(decision.location_value or "").strip()
            if value and not any(normalize_text(value) == normalize_text(current) for current in location_values):
                location_values.append(value)
        if len(location_values) > 1:
            location_action = "conflicto_fuentes"
            location_value = " | ".join(location_values)
            details += " Las fuentes contienen dependencias diferentes; no se modificará la ubicación."
        else:
            location_value = location_values[0] if location_values else ""
            location_action, location_value = _equipment_location_decision(
                record,
                location_value,
                base.master_layout.equipment_location_col,
                location_mode,
            )
            if normalize_text(location_mode) not in {"", "off"}:
                location_letter = col_letter(base.master_layout.equipment_location_col)
                if location_action == "escribir":
                    details += f" Ubicación {location_letter}: se completará con ‘{location_value}’."
                elif location_action == "sobrescribir":
                    details += f" Ubicación {location_letter}: se reemplazará por ‘{location_value}’."

        rows_text = ", ".join(f"{path.name}: fila {decision.report_row}" for path, decision in entries)
        consolidated.append(MatchDecision(
            first.report_row, first.serial_raw, first.serial_key, first.master_row, status,
            f"Fuentes: {rows_text}. {details}", field_results,
            matched_serial_raw=record.serial_raw,
            approximate_match=False,
            source_names=source_names,
            operation_status_action=operation_action,
            operation_status_existing=record.current_status,
            has_positive_counter=has_positive_counter,
            location_action=location_action,
            location_existing=record.current_location,
            location_value=location_value,
            counter_date_action=next((d.counter_date_action for _, d in matched if d.counter_date_value), "conservar"),
            counter_date_existing=record.current_counter_date,
            counter_date_value=next((d.counter_date_value for _, d in matched if d.counter_date_value), ""),
            floor_action=next((d.floor_action for _, d in matched if d.floor_value), "conservar"),
            floor_existing=record.current_floor,
            floor_value=next((d.floor_value for _, d in matched if d.floor_value), ""),
            ip_action=next((d.ip_action for _, d in matched if d.ip_value), "conservar"),
            ip_existing=record.current_ip,
            ip_value=next((d.ip_value for _, d in matched if d.ip_value), ""),
            atlas_ip_action=next((d.atlas_ip_action for _, d in matched if d.atlas_ip_action == "importar"), "conservar"),
            atlas_ip_value=next((d.atlas_ip_value for _, d in matched if d.atlas_ip_value), ""),
        ))

    aggregate_fields: dict[str, int] = {}
    aggregate_headers: dict[str, str] = {}
    for analysis, path in zip(analyses, paths):
        for field_key, index in analysis.mapping.fields.items():
            aggregate_fields.setdefault(field_key, index)
            label = f"[{path.name}] {analysis.mapping.source_headers[field_key]}"
            aggregate_headers[field_key] = aggregate_headers.get(field_key, "") + ("; " if field_key in aggregate_headers else "") + label
    aggregate_mapping = FieldMapping(
        serial_col=base.mapping.serial_col,
        fields=aggregate_fields,
        source_headers=aggregate_headers,
        unmapped=[key for _, _, _, key in TARGETS if key not in aggregate_fields],
    )
    return AnalysisResult(
        master_path=base.master_path,
        report_path=paths[0],
        master_sheet=base.master_sheet,
        master_layout=base.master_layout,
        report_sheet=f"{len(paths)} fuentes",
        report_header_row=0,
        mapping=aggregate_mapping,
        overwrite_existing=overwrite_existing,
        decisions=consolidated,
        master_records=base.master_records,
        report_duplicate_serials=set().union(*(analysis.report_duplicate_serials for analysis in analyses)),
        master_duplicate_serials=base.master_duplicate_serials,
        source_record_count=sum(analysis.source_record_count for analysis in analyses),
        source_unique_count=sum(analysis.source_unique_count for analysis in analyses),
        location_mode=normalize_text(location_mode) or "off",
        auxiliary_mode=normalize_text(auxiliary_mode) or "off",
        import_missing_ips=import_missing_ips,
        atlas_database_path=next((analysis.atlas_database_path for analysis in analyses if analysis.atlas_database_path), None),
    )


def discrepancy_report_path(output_path: Path) -> Path:
    output_path = Path(output_path)
    return output_path.with_name(output_path.stem + "_DISCREPANCIAS.csv")


def write_discrepancy_report(analysis: AnalysisResult, output_path: Path) -> Optional[Path]:
    """Escribe el reporte obligatorio si hay discrepancias; no inventa datos."""
    rows = analysis.discrepancy_rows()
    report_path = discrepancy_report_path(output_path)
    if not rows:
        report_path.unlink(missing_ok=True)
        return None
    fieldnames = [
        "tipo", "fuentes", "fila_reporte", "serie_reporte", "serie_normalizada",
        "serie_maestra", "fila_maestra", "campo", "celda", "valor_reporte",
        "valor_maestro", "accion", "detalle",
    ]
    try:
        with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise AtlasError(f"No se pudo guardar el reporte de discrepancias: {exc}") from exc
    return report_path

def apply_analysis(analysis: AnalysisResult, output_path: Path) -> int:
    output_path = Path(output_path)
    if output_path.suffix.lower() != analysis.master_path.suffix.lower():
        raise AtlasError("La copia de salida debe conservar el mismo formato que la hoja maestra.")
    counter_updates = analysis.updates()
    status_updates = analysis.status_updates()
    location_updates = analysis.location_updates()
    auxiliary_updates = analysis.auxiliary_updates()
    rows_to_update = sorted(set(counter_updates) | set(status_updates) | set(location_updates) | set(auxiliary_updates))
    new_decisions = {
        decision.master_row: decision for decision in analysis.decisions
        if decision.creates_master_row and decision.master_row is not None
    }

    document = open_master_document(analysis.master_path)
    sheet = document.find_sheet((analysis.master_sheet,))
    master_layout = validate_master_layout(
        document,
        sheet,
        analysis.master_layout,
        serial_spec=col_letter(analysis.master_layout.serial_col),
    )
    formulas_before = document.formula_snapshot()
    written = 0

    for row_number in rows_to_update:
        is_new_row = row_number in new_decisions
        if not is_new_row and not (master_layout.first_row <= row_number <= master_layout.last_row):
            raise AtlasError(f"Se bloqueó una fila fuera del rango autorizado: {row_number}")
        if is_new_row and row_number <= master_layout.last_row:
            raise AtlasError(f"Se bloqueó una alta dentro del rango existente: fila {row_number}")
        row = document.get_row(sheet, row_number, split=True)
        if is_new_row:
            decision = new_decisions[row_number]
            serial_cell = document.get_cell(row, master_layout.serial_col, split=True)
            locality_cell = document.get_cell(row, master_layout.locality_col, split=True)
            if document.cell_formula(serial_cell) or document.cell_formula(locality_cell):
                raise AtlasError(f"La fila nueva {row_number} contiene una fórmula protegida.")
            if not is_blank_value(document.cell_value(serial_cell)):
                raise AtlasError(f"La fila nueva {row_number} ya contiene una serie; se canceló la operación.")
            if not is_blank_value(document.cell_value(locality_cell)):
                raise AtlasError(f"La fila nueva {row_number} ya contiene una localidad; se canceló la operación.")
            document.set_text_value(serial_cell, decision.serial_raw)
            document.set_text_value(locality_cell, TARGET_LOCALITY)
        locality = document.cell_value(document.get_cell(row, master_layout.locality_col))
        if normalize_text(locality) != normalize_text(TARGET_LOCALITY):
            raise AtlasError(f"Se bloqueó la fila {row_number}: no pertenece a Torreón.")
        serial_key = normalize_serial(document.cell_value(document.get_cell(row, master_layout.serial_col)))
        expected = analysis.master_records.get(serial_key)
        if expected is None or expected.row_number != row_number:
            raise AtlasError(f"La identidad exacta del equipo cambió en la fila {row_number}; se canceló la operación.")

        for key, value in counter_updates.get(row_number, {}).items():
            if key not in TARGET_BY_KEY:
                raise AtlasError(f"Campo no autorizado bloqueado: {key}")
            _, col, _ = TARGET_BY_KEY[key]
            if col not in TARGET_COLS or col not in AUTHORIZED_WRITE_COLS:
                raise AtlasError(f"Columna no autorizada bloqueada: {col_letter(col)}")
            cell = document.get_cell(row, col, split=True)
            if document.cell_formula(cell):
                raise AtlasError(f"La celda {col_letter(col)}{row_number} contiene una fórmula; se canceló.")
            if isinstance(document, XLSXDocument) and parse_number(value) == 0:
                document.ensure_zero_visible(sheet, row_number, col, cell)
            document.set_numeric_value(cell, value)
            written += 1

        if row_number in status_updates:
            status_col = master_layout.status_col
            if not status_col:
                raise AtlasError("Se solicitó actualizar el estado, pero no se detectó su columna.")
            if status_col in TARGET_COLS:
                raise AtlasError("La columna de estado coincide con una columna de contador; se canceló.")
            status_cell = document.get_cell(row, status_col, split=True)
            if document.cell_formula(status_cell):
                raise AtlasError(f"La celda {col_letter(status_col)}{row_number} contiene una fórmula; se canceló.")
            document.set_text_value(status_cell, status_updates[row_number])
            written += 1

        if row_number in location_updates:
            location_col = master_layout.equipment_location_col
            if not location_col:
                raise AtlasError("Se solicitó actualizar la ubicación, pero no se detectó su columna.")
            protected_cols = {
                master_layout.serial_col,
                master_layout.locality_col,
                master_layout.status_col,
                *TARGET_COLS,
            }
            if location_col in protected_cols:
                raise AtlasError("La columna de ubicación coincide con otra columna protegida; se canceló.")
            location_cell = document.get_cell(row, location_col, split=True)
            if document.cell_formula(location_cell):
                raise AtlasError(
                    f"La celda {col_letter(location_col)}{row_number} contiene una fórmula; se canceló."
                )
            document.set_text_value(location_cell, location_updates[row_number])
            written += 1

        for field_key, value in auxiliary_updates.get(row_number, {}).items():
            auxiliary_columns = {
                "counter_date": master_layout.counter_date_col,
                "floor": master_layout.floor_col,
                "ip": master_layout.ip_col,
            }
            auxiliary_col = auxiliary_columns[field_key]
            protected_cols = {
                master_layout.serial_col, master_layout.locality_col,
                master_layout.status_col, master_layout.equipment_location_col, *TARGET_COLS,
            }
            if not auxiliary_col or auxiliary_col in protected_cols:
                raise AtlasError(f"La columna auxiliar {field_key} no es válida; se canceló la operación.")
            auxiliary_cell = document.get_cell(row, auxiliary_col, split=True)
            if document.cell_formula(auxiliary_cell):
                raise AtlasError(f"La celda {col_letter(auxiliary_col)}{row_number} contiene una fórmula; se canceló.")
            document.set_text_value(auxiliary_cell, value)
            written += 1

    if document.formula_snapshot() != formulas_before:
        raise AtlasError("La verificación detectó un cambio de fórmulas. No se guardó el archivo.")

    document.save(output_path)

    check = open_master_document(output_path)
    check_sheet = check.find_sheet((analysis.master_sheet,))
    if check.formula_snapshot() != formulas_before:
        output_path.unlink(missing_ok=True)
        raise AtlasError("La copia no superó la verificación de fórmulas y fue eliminada.")
    for row_number in rows_to_update:
        row = check.get_row(check_sheet, row_number)
        if row_number in new_decisions:
            decision = new_decisions[row_number]
            actual_serial = normalize_serial(check.cell_value(check.get_cell(row, analysis.master_layout.serial_col)))
            actual_locality = normalize_text(check.cell_value(check.get_cell(row, analysis.master_layout.locality_col)))
            if actual_serial != decision.serial_key or actual_locality != normalize_text(TARGET_LOCALITY):
                output_path.unlink(missing_ok=True)
                raise AtlasError(f"La verificación de la fila nueva {row_number} falló; la copia fue eliminada.")
        for key, expected_value in counter_updates.get(row_number, {}).items():
            _, col, _ = TARGET_BY_KEY[key]
            actual = check.cell_value(check.get_cell(row, col))
            if not numeric_equal(actual, expected_value):
                output_path.unlink(missing_ok=True)
                raise AtlasError(
                    f"La verificación falló en {col_letter(col)}{row_number}; la copia fue eliminada."
                )
        if row_number in status_updates:
            status_col = analysis.master_layout.status_col
            actual_status = str(check.cell_value(check.get_cell(row, status_col)) or "").strip()
            if actual_status != status_updates[row_number]:
                output_path.unlink(missing_ok=True)
                raise AtlasError(
                    f"La verificación falló en {col_letter(status_col)}{row_number}; la copia fue eliminada."
                )
        if row_number in location_updates:
            location_col = analysis.master_layout.equipment_location_col
            actual_location = str(check.cell_value(check.get_cell(row, location_col)) or "").strip()
            if actual_location != location_updates[row_number]:
                output_path.unlink(missing_ok=True)
                raise AtlasError(
                    f"La verificación falló en {col_letter(location_col)}{row_number}; la copia fue eliminada."
                )
        for field_key, expected_value in auxiliary_updates.get(row_number, {}).items():
            auxiliary_col = {
                "counter_date": analysis.master_layout.counter_date_col,
                "floor": analysis.master_layout.floor_col,
                "ip": analysis.master_layout.ip_col,
            }[field_key]
            actual_value = str(check.cell_value(check.get_cell(row, auxiliary_col)) or "").strip()
            if actual_value != str(expected_value).strip():
                output_path.unlink(missing_ok=True)
                raise AtlasError(f"La verificación falló en {col_letter(auxiliary_col)}{row_number}; la copia fue eliminada.")

    try:
        write_discrepancy_report(analysis, output_path)
        _apply_missing_atlas_ips(analysis)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return written


def _apply_missing_atlas_ips(analysis: AnalysisResult) -> int:
    updates = analysis.atlas_ip_updates()
    if not updates:
        return 0
    database = analysis.atlas_database_path
    if database is None or not database.exists():
        raise AtlasError("No se encontró la base de Atlas para importar las IP faltantes.")
    backup = database.with_name(database.stem + "_ANTES_IP_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + database.suffix)
    shutil.copy2(database, backup)
    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        written = 0
        for serial, ip_value in updates.items():
            if not normalize_ip(ip_value):
                raise AtlasError(f"La IP propuesta para {serial} no es válida.")
            matches = connection.execute(
                "SELECT id, ip_address FROM atlas_equipment WHERE upper(replace(replace(trim(serial_number), '-', ''), ' ', '')) = ?",
                (serial,),
            ).fetchall()
            if len(matches) != 1:
                raise AtlasError(f"No se pudo identificar de forma única la serie {serial} en Atlas.")
            equipment_id, current_ip = matches[0]
            if str(current_ip or "").strip():
                continue
            cursor = connection.execute(
                "UPDATE atlas_equipment SET ip_address = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND trim(coalesce(ip_address, '')) = ''",
                (ip_value, equipment_id),
            )
            written += cursor.rowcount
        connection.commit()
        return written
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

def analysis_as_dict(analysis: AnalysisResult) -> dict[str, Any]:
    return {
        "app_version": APP_VERSION,
        "master": str(analysis.master_path),
        "report": str(analysis.report_path),
        "master_sheet": analysis.master_sheet,
        "master_layout": {
            "header_row": analysis.master_layout.header_row,
            "serial_column": col_letter(analysis.master_layout.serial_col),
            "locality_column": col_letter(analysis.master_layout.locality_col),
            "equipment_location_column": (
                col_letter(analysis.master_layout.equipment_location_col)
                if analysis.master_layout.equipment_location_col else ""
            ),
            "counter_date_column": col_letter(analysis.master_layout.counter_date_col) if analysis.master_layout.counter_date_col else "",
            "floor_column": col_letter(analysis.master_layout.floor_col) if analysis.master_layout.floor_col else "",
            "ip_column": col_letter(analysis.master_layout.ip_col) if analysis.master_layout.ip_col else "",
            "target_range": f"{target_range_label()} · filas {analysis.master_layout.first_row}:{analysis.master_layout.last_row}",
            "validation": analysis.master_layout.validation_mode,
        },
        "report_sheet": analysis.report_sheet,
        "report_header_row": analysis.report_header_row,
        "overwrite_existing": analysis.overwrite_existing,
        "mapping": {
            "serial": analysis.mapping.serial_col + 1,
            "fields": {
                key: {
                    "source_column": index + 1,
                    "source_header": analysis.mapping.source_headers[key],
                    "target": TARGET_BY_KEY[key][0],
                }
                for key, index in analysis.mapping.fields.items()
            },
            "unmapped": analysis.mapping.unmapped,
        },
        "counts": analysis.counts(),
        "decisions": [
            {
                "report_row": item.report_row,
                "sources": item.source_names,
                "serial": item.serial_raw,
                "master_row": item.master_row,
                "matched_serial": item.matched_serial_raw or None,
                "approximate_match": item.approximate_match,
                "status": item.status,
                "details": item.details,
                "fields": [
                    {
                        "target": field.target_letter,
                        "source_header": field.source_header,
                        "source_value": field.source_value,
                        "existing_value": field.existing_value,
                        "action": field.action,
                    }
                    for field in item.fields
                ],
            }
            for item in analysis.decisions
        ],
    }


def print_analysis(analysis: AnalysisResult) -> None:
    counts = analysis.counts()
    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"Hoja maestra: {analysis.master_sheet}")
    print(
        f"Disposición detectada: encabezado fila {analysis.master_layout.header_row}; "
        f"Serie={col_letter(analysis.master_layout.serial_col)}; "
        f"LOCALIDAD={col_letter(analysis.master_layout.locality_col)}; destinos={target_range_label()}"
    )
    print(f"Validación maestra: {analysis.master_layout.validation_mode}")
    print(f"Hoja del reporte: {analysis.report_sheet} (encabezado fila {analysis.report_header_row})")
    print("Mapeo detectado:")
    for key, source_col in analysis.mapping.fields.items():
        letter, _, target_label = TARGET_BY_KEY[key]
        print(f"  {analysis.mapping.source_headers[key]!r} -> {letter} ({target_label})")
    if analysis.mapping.unmapped:
        print("Campos maestros sin fuente en el reporte: " + ", ".join(TARGET_BY_KEY[k][0] for k in analysis.mapping.unmapped))
    print("Resumen:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")


class AtlasGUI:
    def __init__(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox, ttk
        except ImportError as exc:
            raise AtlasError(
                "Tkinter no está instalado. En Kubuntu puede instalarse con: sudo apt install python3-tk"
            ) from exc

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.minsize(1050, 680)
        self.analysis: Optional[AnalysisResult] = None

        self.master_var = tk.StringVar()
        self.report_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Seleccione la hoja maestra y el reporte de contadores.")
        self.summary_var = tk.StringVar(value="Sin análisis")
        self._build()

    def _build(self) -> None:
        ttk = self.ttk
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        files_frame = ttk.LabelFrame(root, text="Archivos", padding=12)
        files_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        files_frame.columnconfigure(1, weight=1)

        ttk.Label(files_frame, text="Hoja maestra XLSX u ODS:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(files_frame, textvariable=self.master_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(files_frame, text="Examinar…", command=self.select_master).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(files_frame, text="Reporte de contadores:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(files_frame, textvariable=self.report_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(files_frame, text="Examinar…", command=self.select_report).grid(row=1, column=2, padx=(8, 0), pady=4)

        options = ttk.Frame(root, padding=(12, 4))
        options.grid(row=1, column=0, sticky="ew")
        ttk.Checkbutton(
            options,
            text="Permitir reemplazar valores ya existentes en AK–AR (nunca fórmulas)",
            variable=self.overwrite_var,
            command=self.invalidate_analysis,
        ).pack(side="left")
        ttk.Button(options, text="Analizar y preparar vista previa", command=self.run_analysis).pack(side="right")

        preview = ttk.Panedwindow(root, orient="vertical")
        preview.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

        top = ttk.Frame(preview)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(1, weight=1)
        ttk.Label(top, textvariable=self.summary_var, font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))

        columns = ("serial", "report_row", "master_row", "status", "cells", "details")
        self.tree = ttk.Treeview(top, columns=columns, show="headings", height=16)
        headings = {
            "serial": "Número de serie",
            "report_row": "Fila reporte",
            "master_row": "Fila maestra",
            "status": "Estado",
            "cells": "Celdas",
            "details": "Detalle",
        }
        widths = {"serial": 150, "report_row": 90, "master_row": 90, "status": 135, "cells": 90, "details": 430}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        yscroll = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self.show_details)
        preview.add(top, weight=3)

        bottom = ttk.LabelFrame(preview, text="Mapeo y detalle de la selección", padding=8)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)
        self.detail = self.tk.Text(bottom, height=10, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(bottom, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        preview.add(bottom, weight=2)

        footer = ttk.Frame(root, padding=(12, 6, 12, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.generate_button = ttk.Button(footer, text="Generar copia local", command=self.generate, state="disabled")
        self.generate_button.grid(row=0, column=1, sticky="e")

    def select_master(self) -> None:
        path = self.filedialog.askopenfilename(
            title="Seleccionar hoja maestra",
            filetypes=[
                ("Hojas maestras compatibles", "*.xlsx *.ods"),
                ("Excel", "*.xlsx"),
                ("OpenDocument Spreadsheet", "*.ods"),
            ],
        )
        if path:
            self.master_var.set(path)
            self.invalidate_analysis()

    def select_report(self) -> None:
        path = self.filedialog.askopenfilename(
            title="Seleccionar reporte de contadores",
            filetypes=[
                ("Reportes compatibles", "*.csv *.xlsx *.ods"),
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx"),
                ("OpenDocument Spreadsheet", "*.ods"),
            ],
        )
        if path:
            self.report_var.set(path)
            self.invalidate_analysis()

    def invalidate_analysis(self) -> None:
        self.analysis = None
        self.generate_button.configure(state="disabled")
        self.status_var.set("Los archivos u opciones cambiaron. Ejecute nuevamente el análisis.")

    def run_analysis(self) -> None:
        master = self.master_var.get().strip()
        report = self.report_var.get().strip()
        if not master or not report:
            self.messagebox.showwarning(APP_NAME, "Seleccione la hoja maestra y el reporte.")
            return
        self.status_var.set("Analizando coincidencias y campos compatibles…")
        self.root.update_idletasks()
        try:
            analysis = analyze_files(Path(master), Path(report), self.overwrite_var.get())
        except Exception as exc:
            self.analysis = None
            self.generate_button.configure(state="disabled")
            self.status_var.set("El análisis no pudo completarse.")
            self.messagebox.showerror(APP_NAME, str(exc))
            return
        self.analysis = analysis
        self.populate_preview()
        writable = analysis.counts().get("writable_cells", 0)
        self.generate_button.configure(state="normal" if (writable or analysis.counts().get("discrepancies", 0)) else "disabled")
        self.status_var.set("Vista previa terminada. El archivo maestro no ha sido modificado.")

    def populate_preview(self) -> None:
        assert self.analysis is not None
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, decision in enumerate(self.analysis.decisions):
            writable_cells = [
                field.target_letter for field in decision.fields
                if field.action in {"escribir", "sobrescribir", "escribir_cero"}
            ]
            cells = ", ".join(writable_cells) or "—"
            self.tree.insert("", "end", iid=str(index), values=(
                decision.serial_raw,
                decision.report_row,
                decision.master_row or "—",
                decision.status.replace("_", " "),
                cells,
                decision.details,
            ))
        counts = self.analysis.counts()
        self.summary_var.set(
            f"{counts.get('report_rows', 0)} registros · "
            f"{counts.get('writable_equipment', 0)} equipos listos · "
            f"{counts.get('writable_cells', 0)} celdas · "
            f"{counts.get('zero_fill_cells', 0)} ceros de complemento · "
            f"{counts.get('conflict_cells', 0)} conflictos · "
            f"{counts.get('discrepancies', 0)} discrepancias"
        )
        mapping_lines = [
            "ESTRUCTURA DE LA HOJA MAESTRA:",
            f"• Encabezados detectados en fila {self.analysis.master_layout.header_row}.",
            f"• Número de serie: columna {col_letter(self.analysis.master_layout.serial_col)}.",
            f"• LOCALIDAD: columna {col_letter(self.analysis.master_layout.locality_col)}.",
            f"• Destinos autorizados: AK–AR, filas {MASTER_FIRST_ROW}–{MASTER_LAST_ROW}.",
            "• Coincidencia obligatoria: número de serie exacto normalizado; no se usan aproximaciones OCR.",
            "• Toda discrepancia se guarda en un CSV adicional.",
            f"• Validación: {self.analysis.master_layout.validation_mode}.",
            "",
            "MAPEO DETECTADO (reporte → hoja maestra):",
        ]
        for key, source_col in self.analysis.mapping.fields.items():
            letter, _, label = TARGET_BY_KEY[key]
            mapping_lines.append(
                f"• Columna {source_col + 1} del reporte, “{self.analysis.mapping.source_headers[key]}” → {letter}, “{label}”"
            )
        if self.analysis.mapping.unmapped:
            mapping_lines.append("\nSin campo compatible en el reporte: " + ", ".join(TARGET_BY_KEY[k][0] for k in self.analysis.mapping.unmapped) + ". Para cada equipo realmente actualizado, las celdas vacías de estos campos se completarán con 0.")
        self.set_detail("\n".join(mapping_lines))

    def show_details(self, _event=None) -> None:
        if self.analysis is None:
            return
        selection = self.tree.selection()
        if not selection:
            return
        decision = self.analysis.decisions[int(selection[0])]
        lines = [
            f"Serie: {decision.serial_raw}",
            f"Fila del reporte: {decision.report_row}",
            f"Fila maestra: {decision.master_row or 'No encontrada'}",
            f"Estado: {decision.status}",
            decision.details,
            "",
        ]
        for item in decision.fields:
            lines.append(
                f"{item.target_letter} · {item.target_label}\n"
                f"  Fuente: {item.source_header} = {display_number(item.source_value) or 'sin dato'}\n"
                f"  Existente: {display_number(item.existing_value) or 'vacío'}\n"
                f"  Acción: {item.action}\n"
            )
        self.set_detail("\n".join(lines))

    def set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def generate(self) -> None:
        if self.analysis is None:
            self.messagebox.showwarning(APP_NAME, "Primero ejecute el análisis.")
            return
        master = Path(self.analysis.master_path)
        extension = master.suffix.lower()
        default_name = master.stem + f"_CONTADORES_{target_range_label().replace(':', '-')}_TORREON" + extension
        output = self.filedialog.asksaveasfilename(
            title="Guardar copia actualizada",
            defaultextension=extension,
            initialdir=str(master.parent),
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")] if extension == ".xlsx" else [("OpenDocument Spreadsheet", "*.ods")],
        )
        if not output:
            return
        self.status_var.set("Generando y verificando la copia local…")
        self.root.update_idletasks()
        try:
            written = apply_analysis(self.analysis, Path(output))
        except Exception as exc:
            self.status_var.set("No se generó ninguna copia.")
            self.messagebox.showerror(APP_NAME, str(exc))
            return
        equipment = len(self.analysis.updates())
        self.status_var.set(f"Copia verificada: {equipment} equipos y {written} celdas insertadas.")
        self.messagebox.showinfo(
            APP_NAME,
            f"Proceso terminado.\n\nSe actualizaron {equipment} equipos y {written} celdas exclusivamente en {target_range_label()} para Torreón. "
            f"La columna H y todas las columnas fuera de {target_range_label()} permanecieron intactas. "
            f"Los campos vacíos autorizados de esos equipos se completaron con 0.\n\nArchivo:\n{output}"
        )

    def run(self) -> None:
        self.root.mainloop()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, help="Hoja maestra XLSX u ODS")
    parser.add_argument("--report", type=Path, help="Reporte CSV, XLSX u ODS")
    parser.add_argument("--output", type=Path, help="Copia local de salida, con el mismo formato que la hoja maestra")
    parser.add_argument("--target-range", default="AK:AR", help="Bloque mensual de ocho columnas, por ejemplo AK:AR o AS")
    parser.add_argument("--overwrite-existing", action="store_true", help="Permite reemplazar valores existentes en el bloque seleccionado")
    parser.add_argument("--analyze-only", action="store_true", help="Analiza sin generar archivo")
    parser.add_argument("--json", dest="json_path", type=Path, help="Guarda la vista previa en JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cli_mode = args.master is not None or args.report is not None or args.output is not None or args.analyze_only
    if not cli_mode:
        try:
            AtlasGUI().run()
            return 0
        except AtlasError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if args.master is None or args.report is None:
        parser.error("En modo consola debe indicar --master y --report.")
    try:
        configure_target_range(args.target_range)
        analysis = analyze_files(args.master, args.report, args.overwrite_existing)
        print_analysis(analysis)
        if args.json_path:
            args.json_path.write_text(json.dumps(analysis_as_dict(analysis), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Vista previa JSON: {args.json_path}")
        if args.analyze_only:
            return 0
        if args.output is None:
            parser.error("Indique --output o use --analyze-only.")
        written = apply_analysis(analysis, args.output)
        print(f"Copia generada y verificada: {args.output}")
        print(f"Equipos actualizados: {len(analysis.updates())}")
        print(f"Celdas insertadas: {written}")
        report_path = discrepancy_report_path(args.output)
        if report_path.exists():
            print(f"Reporte de discrepancias: {report_path}")
        else:
            print("No se detectaron discrepancias.")
        return 0
    except AtlasError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
