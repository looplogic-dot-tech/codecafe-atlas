from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence


EXPORT_REPORT_FILENAME = "reporte_exportacion.csv"
EXPORT_REPORT_HEADERS = (
    "Archivo origen",
    "Página",
    "Número de serie / folio",
    "Categoría",
    "Fecha reporte",
    "Método",
    "Confianza OCR (%)",
    "Ruta PDF en ZIP",
)


def build_export_report_csv(rows: Iterable[Sequence[object]]) -> bytes:
    """Return an Excel-friendly UTF-8 CSV report with a BOM."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_REPORT_HEADERS)
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
