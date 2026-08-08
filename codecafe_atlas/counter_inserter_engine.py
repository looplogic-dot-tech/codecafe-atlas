#!/usr/bin/env python3
"""
CodeCafe Atlas — Insertador exacto de contadores local v1.0.14

Objetivo estricto:
- Leer una hoja maestra XLSX u ODS.
- Leer un reporte compatible de CodeCafe Atlas (CSV, XLSX u ODS).
- Relacionar equipos por número de serie.
- Trabajar exclusivamente en la hoja de consumo, filas 821–1404.
- Trabajar exclusivamente con registros cuya LOCALIDAD sea Torreón.
- Escribir contadores exclusivamente en AK:AR.
- No agregar columnas, hojas ni campos.
- No modificar fórmulas.
- Completar con 0 las celdas realmente vacías de AK–AR para cada serie exacta con al menos un contador válido.
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
import json
import os
import posixpath
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

APP_NAME = "CodeCafe Atlas — Insertador inteligente de contadores"
APP_VERSION = "1.0.14-exact"

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
STATUS_COL = 8              # H
STATUS_LETTER = "H"
STATUS_VALUE = "En Operación"
TARGET_LOCALITY = "Torreón"
TARGET_MONTH = "Julio"

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
AUTHORIZED_WRITE_COLS = TARGET_COLS

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


def col_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


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


@dataclass
class TableData:
    source_path: Path
    sheet_name: str
    header_row: int
    headers: list[str]
    rows: list[list[Any]]


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
    validation_mode: str


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

    @property
    def counter_writable_count(self) -> int:
        return sum(1 for item in self.fields if item.action in {"escribir", "sobrescribir", "escribir_cero"})

    @property
    def writable_count(self) -> int:
        return self.counter_writable_count

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
        return rows

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
        """v1.0.14: el insertador no modifica H ni ninguna columna fuera de AK–AR."""
        return {}


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


def read_report(path: Path) -> TableData:
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
        mapping = detect_mapping(table.headers, allow_partial=True)
        mapped = len(mapping.fields)
        july_hits = sum(1 for header in table.headers if "julio" in normalize_text(header))
        return mapped * 100 + july_hits * 10 + min(len(table.rows), 100)

    best = max(candidates, key=candidate_score)
    detect_mapping(best.headers, allow_partial=False)  # valida antes de devolver
    return best


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
        elif "total de impresiones" in h and "equivalent" not in h and has_july:
            score = 160
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
    anchor_candidates: dict[str, list[tuple[int, int]]] = {"principal": [], "equivalente": []}
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
    for key in ("duplex", "atascos", "escaneos", "copias", "color", "digitalizaciones"):
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
        raise AtlasError("No se reconoció ningún campo de contador compatible con AK–AR.")
    unmapped = [key for key in TARGET_BY_KEY if key not in fields]
    return FieldMapping(serial_col, fields, source_headers, unmapped)


def locality_header_score(header: Any) -> int:
    h = normalize_text(header)
    if h == "localidad":
        return 120
    if "localidad" in h:
        return 105
    if h in {"ciudad", "municipio"}:
        return 35
    return 0


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


def detect_master_layout(document: ODSDocument | XLSXDocument, sheet: ET.Element) -> MasterLayout:
    """Detecta la disposición real del maestro sin asumir que Serie está en E.

    La hoja oficial descargada como XLSX puede conservar una disposición donde
    E=Modelo y F=N.° de Serie, mientras que la copia ODS usada inicialmente tiene
    E=N.° de Serie y F=Modelo. AK:AR permanecen como el bloque autorizado.
    """
    candidates: list[tuple[int, int, int, int]] = []
    for row_number in range(1, MASTER_HEADER_SCAN_ROWS + 1):
        row = document.get_row(sheet, row_number)
        serial_candidates: list[tuple[int, int]] = []
        locality_candidates: list[tuple[int, int]] = []
        for col in range(1, TARGET_LAST_COL + 1):
            value = document.cell_value(document.get_cell(row, col))
            serial_score = serial_header_score(normalize_text(value))
            if serial_score:
                serial_candidates.append((serial_score, col))
            locality_score = locality_header_score(value)
            if locality_score:
                locality_candidates.append((locality_score, col))
        if not serial_candidates or not locality_candidates:
            continue
        serial_score, serial_col = max(serial_candidates, key=lambda item: (item[0], -item[1]))
        locality_score, locality_col = max(locality_candidates, key=lambda item: (item[0], -item[1]))
        if serial_col == locality_col:
            continue
        # Favorece una fila compacta y la localidad en el bloque administrativo.
        score = serial_score + locality_score - abs(locality_col - serial_col)
        candidates.append((score, -row_number, serial_col, locality_col))

    if candidates:
        _, negative_row, serial_col, locality_col = max(candidates)
        header_row = -negative_row
    else:
        preview = _master_header_preview(document, sheet)
        raise AtlasError(
            "No se localizaron automáticamente los encabezados de N.° de Serie y LOCALIDAD "
            f"en las primeras {MASTER_HEADER_SCAN_ROWS} filas. No se realizará ninguna escritura. "
            + (f"Contenido observado: {preview}" if preview else "")
        )

    # Confirmación estructural con registros reales dentro del rango autorizado.
    torreon_records = 0
    nonempty_serials = 0
    target_evidence = 0
    for row_number in range(MASTER_FIRST_ROW, MASTER_LAST_ROW + 1):
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

    if nonempty_serials == 0:
        raise AtlasError(
            f"La columna detectada para número de serie ({col_letter(serial_col)}) no contiene equipos "
            f"entre las filas {MASTER_FIRST_ROW} y {MASTER_LAST_ROW}. No se realizará ninguna escritura."
        )
    if torreon_records == 0:
        raise AtlasError(
            f"No se encontraron equipos de Torreón usando Serie={col_letter(serial_col)} y "
            f"LOCALIDAD={col_letter(locality_col)} entre las filas {MASTER_FIRST_ROW}–{MASTER_LAST_ROW}. "
            "No se realizará ninguna escritura."
        )

    # Los encabezados de AK:AR pueden estar distribuidos en varias filas o celdas
    # combinadas en el XLSX. Se usan como evidencia adicional, no como requisito rígido.
    target_header_hits = 0
    target_tokens = {
        37: ("impresion", "carta", "julio"),
        38: ("impresion", "equivalent", "oficio", "julio"),
        39: ("ambas caras", "duplex", "julio"),
        40: ("atasco", "julio"),
        41: ("escaneo",),
        42: ("copias",),
        43: ("color",),
        44: ("digital",),
    }
    for col, tokens in target_tokens.items():
        combined = " ".join(
            normalize_text(document.cell_value(document.get_cell(document.get_row(sheet, row_number), col)))
            for row_number in range(1, MASTER_HEADER_SCAN_ROWS + 1)
        )
        if any(token in combined for token in tokens):
            target_header_hits += 1

    validation_mode = (
        f"encabezados detectados; {target_header_hits}/8 campos AK–AR reconocidos"
        if target_header_hits
        else f"encabezados de AK–AR distribuidos o vacíos; bloque confirmado por {target_evidence} celdas existentes"
    )
    return MasterLayout(header_row, serial_col, locality_col, validation_mode)


def validate_master_layout(
    document: ODSDocument | XLSXDocument,
    sheet: ET.Element,
    expected: Optional[MasterLayout] = None,
) -> MasterLayout:
    layout = detect_master_layout(document, sheet)
    if expected is not None and (
        layout.serial_col != expected.serial_col
        or layout.locality_col != expected.locality_col
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
    for row_number in range(MASTER_FIRST_ROW, MASTER_LAST_ROW + 1):
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
        status_cell = document.get_cell(row, STATUS_COL)
        current_status = document.cell_value(status_cell)
        status_has_formula = bool(document.cell_formula(status_cell))
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


def analyze_files(master_path: Path, report_path: Path, overwrite_existing: bool = False) -> AnalysisResult:
    master_path = Path(master_path)
    report_path = Path(report_path)
    document = open_master_document(master_path)
    sheet = document.find_sheet()
    master_sheet_name = document.sheet_name(sheet)
    master_layout = validate_master_layout(document, sheet)
    master_records, master_duplicates = load_master_records(document, sheet, master_layout)

    report = read_report(report_path)
    mapping = detect_mapping(report.headers)

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

        record = master_records.get(serial_key)
        if record is None:
            decisions.append(MatchDecision(
                report_row, serial_raw, serial_key, None, "no_encontrado",
                "No existe una coincidencia exacta del número de serie normalizado en Torreón, filas 821–1404. No se intentó ninguna corrección aproximada."
            ))
            continue

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
        elif writable:
            status = "listo_con_discrepancias" if discrepancies else "listo"
            details = f"Coincidencia exacta. {writable} celda(s) de AK–AR lista(s) para escribir."
            if discrepancies:
                details += f" {discrepancies} discrepancia(s) se documentarán en el CSV adicional."
        elif discrepancies:
            status = "discrepancia"
            details = f"Coincidencia exacta, pero {discrepancies} discrepancia(s) impiden escrituras automáticas en las celdas afectadas."
        else:
            status = "sin_cambios"
            details = "La serie coincide exactamente y los valores ya son iguales o no requieren cambios."

        decisions.append(MatchDecision(
            report_row, serial_raw, serial_key, record.row_number, status, details, field_decisions,
            matched_serial_raw=record.serial_raw,
            approximate_match=False,
            operation_status_action="conservar",
            operation_status_existing=record.current_status,
            has_positive_counter=has_positive_counter,
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
    )



def analyze_multiple_files(
    master_path: Path,
    report_paths: list[Path],
    overwrite_existing: bool = False,
) -> AnalysisResult:
    """Consolida varias fuentes usando exclusivamente la serie exacta normalizada."""
    paths = [Path(path) for path in report_paths]
    if not paths:
        raise AtlasError("Seleccione al menos un reporte fuente.")
    if len(paths) == 1:
        result = analyze_files(master_path, paths[0], overwrite_existing)
        for decision in result.decisions:
            decision.source_names = paths[0].name
            for item in decision.fields:
                item.source_header = f"[{paths[0].name}] {item.source_header}"
        return result

    analyses = [analyze_files(master_path, path, overwrite_existing) for path in paths]
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

        rows_text = ", ".join(f"{path.name}: fila {decision.report_row}" for path, decision in entries)
        consolidated.append(MatchDecision(
            first.report_row, first.serial_raw, first.serial_key, first.master_row, status,
            f"Fuentes: {rows_text}. {details}", field_results,
            matched_serial_raw=record.serial_raw,
            approximate_match=False,
            source_names=source_names,
            operation_status_action="conservar",
            operation_status_existing=record.current_status,
            has_positive_counter=has_positive_counter,
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
    rows_to_update = sorted(counter_updates)

    document = open_master_document(analysis.master_path)
    sheet = document.find_sheet((analysis.master_sheet,))
    master_layout = validate_master_layout(document, sheet, analysis.master_layout)
    formulas_before = document.formula_snapshot()
    written = 0

    for row_number in rows_to_update:
        if not (MASTER_FIRST_ROW <= row_number <= MASTER_LAST_ROW):
            raise AtlasError(f"Se bloqueó una fila fuera del rango autorizado: {row_number}")
        row = document.get_row(sheet, row_number, split=True)
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
        for key, expected_value in counter_updates.get(row_number, {}).items():
            _, col, _ = TARGET_BY_KEY[key]
            actual = check.cell_value(check.get_cell(row, col))
            if not numeric_equal(actual, expected_value):
                output_path.unlink(missing_ok=True)
                raise AtlasError(
                    f"La verificación falló en {col_letter(col)}{row_number}; la copia fue eliminada."
                )

    try:
        write_discrepancy_report(analysis, output_path)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return written

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
            "target_range": f"AK{MASTER_FIRST_ROW}:AR{MASTER_LAST_ROW}",
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
        f"LOCALIDAD={col_letter(analysis.master_layout.locality_col)}; destinos=AK:AR"
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
        default_name = master.stem + "_CONTADORES_JULIO_TORREON" + extension
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
            f"Proceso terminado.\n\nSe actualizaron {equipment} equipos y {written} celdas en H y AK–AR para Torreón. "
            f'H se estableció como “{STATUS_VALUE}” solo donde existía al menos un contador mayor a 0. '
            f"Los campos vacíos autorizados de esos equipos se completaron con 0.\n\nArchivo:\n{output}"
        )

    def run(self) -> None:
        self.root.mainloop()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, help="Hoja maestra XLSX u ODS")
    parser.add_argument("--report", type=Path, help="Reporte CSV, XLSX u ODS")
    parser.add_argument("--output", type=Path, help="Copia local de salida, con el mismo formato que la hoja maestra")
    parser.add_argument("--overwrite-existing", action="store_true", help="Permite reemplazar valores existentes en AK–AR")
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
