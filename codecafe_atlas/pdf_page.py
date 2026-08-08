from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz
from PIL import Image

from .export_report import EXPORT_REPORT_FILENAME, build_export_report_csv
from .output_filename import next_available_path
from .separator_history import (
    append_export_history,
    clear_export_history,
    load_export_history,
    separator_history_path,
)
from .service_report_date import (
    date_folder_names,
    display_report_date,
    extract_provider_report_date,
    format_manual_report_date_input,
    parse_manual_report_date,
)
from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import pytesseract
except ImportError:
    pytesseract = None


# Formatos HP encontrados en los reportes usados por CodeCafe Atlas.
# No se exige un límite de palabra al final porque el OCR puede pegar la
# siguiente palabra al número de serie: VNB0B01173CONFIGURACION.
HP_SERIAL_PATTERNS = [
    re.compile(r"(?<![A-Z0-9])(VNB0B\d{5})", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])(VNB\d{6})", re.IGNORECASE),
]

SERIAL_LABEL_PATTERNS = [
    re.compile(
        r"(?:n[uú]mero|n[úu]m\.?|no\.?)\s+(?:de\s+)?serie\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9_-]{5,31})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:serial(?:\s+number)?|s\/n)\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9_-]{5,31})",
        re.IGNORECASE,
    ),
]


SERVICE_REPORT_LABEL_PATTERNS = [
    re.compile(
        r"(?:no\.?\s+de\s+)?reporte\s+asignado\s+por\s+el\s+prestador\s+de\s+servicio\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9_./-]{4,31})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:folio|orden\s+de\s+servicio|c[eé]dula)\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9_./-]{4,31})",
        re.IGNORECASE,
    ),
]
SERVICE_REQ_PATTERN = re.compile(r"\b(?:[A-Z][A-Z0-9]{2,31}[-_/ ]+)?REQ[-_/ ]*\d{4,10}\b", re.IGNORECASE)
SERVICE_DGTI_PATTERN = re.compile(r"\b[A-Z]{1,3}[-_/ ]*\d{5,10}\b", re.IGNORECASE)

GENERIC_CANDIDATE = re.compile(r"\b[A-Z0-9]{8,18}\b", re.IGNORECASE)

OCR_TRANSLATION = str.maketrans({
    " ": "",
    "-": "",
    "_": "",
})

INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class PageResult:
    source_path: str
    source_name: str
    page_index: int
    page_number: int
    serial: str
    method: str
    confidence: int
    preview_text: str
    thumbnail_png: bytes
    category: str = ""
    category_confidence: int = 0
    report_date: str = ""
    report_date_confidence: int = 0
    deleted: bool = False


def normalize_serial(value: str) -> str:
    cleaned = value.upper().strip().translate(OCR_TRANSLATION)
    cleaned = re.sub(r"[^A-Z0-9]", "", cleaned)
    return cleaned[:32]


def trim_detected_serial(value: str) -> str:
    """Trim text that OCR may have joined after a recognized serial.

    This is applied only to automatic detections. Values typed manually are
    preserved, except for normal removal of spaces and punctuation.
    """
    candidate = normalize_serial(value)
    for pattern in HP_SERIAL_PATTERNS:
        match = pattern.match(candidate)
        if match:
            return normalize_serial(match.group(1))
    return candidate


def extract_serial(text: str) -> tuple[str, int]:
    if not text:
        return "", 0

    normalized_text = text.upper()

    # Search known HP formats first. The regex ends after the expected digits
    # even if OCR joins the following word without a space.
    for pattern in HP_SERIAL_PATTERNS:
        match = pattern.search(normalized_text)
        if match:
            return normalize_serial(match.group(1)), 98

    for pattern in SERIAL_LABEL_PATTERNS:
        match = pattern.search(normalized_text)
        if match:
            candidate = trim_detected_serial(match.group(1))
            if 7 <= len(candidate) <= 24:
                return candidate, 94

    candidates = []
    for match in GENERIC_CANDIDATE.findall(normalized_text):
        candidate = normalize_serial(match)
        if (
            8 <= len(candidate) <= 18
            and any(char.isdigit() for char in candidate)
            and any(char.isalpha() for char in candidate)
            and not candidate.startswith(("WINDOWS", "LASERJET", "PRORES"))
        ):
            candidates.append(candidate)

    return (candidates[0], 58) if candidates else ("", 0)



def extract_service_report(text: str) -> tuple[str, int]:
    """Extract the service provider report/folio from a service certificate."""
    if not text:
        return "", 0
    normalized = " ".join(text.upper().split())

    # The provider report (normally REQ...) is the preferred file identifier.
    req = SERVICE_REQ_PATTERN.search(normalized)
    if req:
        return normalize_service_identifier(req.group(0)), 96

    for pattern in SERVICE_REPORT_LABEL_PATTERNS:
        match = pattern.search(normalized)
        if match:
            candidate = normalize_service_identifier(match.group(1))
            if len(candidate) >= 5:
                return candidate, 92

    dgti = SERVICE_DGTI_PATTERN.search(normalized)
    if dgti:
        return normalize_service_identifier(dgti.group(0)), 70
    return "", 0


def format_manual_service_identifier_input(value: str) -> str:
    """Format compact DGTI/service folios as PREFIX-NUMBER.

    Examples: R015422 -> R-015422 and REQ12345 -> REQ-12345.
    Existing separators in more complex identifiers are preserved so legacy
    provider folios continue to work.
    """
    cleaned = (value or "").upper().strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[^A-Z0-9._/-]", "", cleaned)

    compact_match = re.fullmatch(r"([A-Z]{1,3})[-_/]?(\d{1,10})", cleaned)
    if compact_match:
        prefix, digits = compact_match.groups()
        return f"{prefix}-{digits}"[:40]

    return cleaned[:40]


def normalize_service_identifier(value: str) -> str:
    return format_manual_service_identifier_input(value)


def find_session_duplicate_identifier(
    results: list[PageResult],
    identifier: str,
    *,
    exclude_row: int | None = None,
) -> int | None:
    """Return the row already using a service folio in the current session.

    The check is deliberately limited to the in-memory ``results`` collection.
    It does not consult history or the database, so the same folio can be used
    again after starting a new separator session.
    """
    normalized = normalize_service_identifier(identifier)
    if not normalized:
        return None

    for row, result in enumerate(results):
        if row == exclude_row or result.deleted or not result.serial:
            continue
        if normalize_service_identifier(result.serial) == normalized:
            return row
    return None


def normalize_for_classification(text: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFD", text or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.lower()
    return re.sub(r"\s+", " ", value)


def classify_service_text(text: str, rules: list[tuple[str, list[str]]], fallback: str) -> tuple[str, int]:
    normalized = normalize_for_classification(text)
    best_category = ""
    best_score = 0
    for category, keywords in rules:
        score = 0
        for keyword in keywords:
            token = normalize_for_classification(keyword).strip()
            if token and token in normalized:
                score += max(1, len(token.split()))
        if score > best_score:
            best_category = category
            best_score = score
    if best_category:
        return best_category, min(99, 70 + best_score * 6)
    return fallback, 45


def render_service_failure_for_ocr(page: fitz.Page) -> Image.Image:
    """Render the central failure-description area of a service certificate."""
    rect = page.rect
    clip = fitz.Rect(rect.x0, rect.y0 + rect.height * 0.24, rect.x1, rect.y0 + rect.height * 0.53)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=clip, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("L")
    from PIL import ImageEnhance, ImageFilter, ImageOps
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.8)
    return image.filter(ImageFilter.SHARPEN)


def render_service_header_for_ocr(page: fitz.Page) -> Image.Image:
    """Render the upper portion at high resolution for printed/handwritten folios."""
    rect = page.rect
    clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.38)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.2, 3.2), clip=clip, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("L")
    from PIL import ImageEnhance, ImageFilter, ImageOps
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.7)
    image = image.filter(ImageFilter.SHARPEN)
    return image

def render_service_date_for_ocr(page: fitz.Page, *, value_only: bool = False) -> Image.Image:
    """Render the provider-report date field at high resolution.

    The first crop keeps the printed label so the date can be tied to the exact
    field. The narrower fallback crop contains only the handwritten value and is
    used when OCR cannot read the label.
    """
    rect = page.rect
    if value_only:
        clip = fitz.Rect(
            rect.x0 + rect.width * 0.56,
            rect.y0 + rect.height * 0.115,
            rect.x1,
            rect.y0 + rect.height * 0.225,
        )
    else:
        clip = fitz.Rect(
            rect.x0 + rect.width * 0.38,
            rect.y0 + rect.height * 0.07,
            rect.x1,
            rect.y0 + rect.height * 0.31,
        )
    pix = page.get_pixmap(matrix=fitz.Matrix(4.0, 4.0), clip=clip, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("L")
    from PIL import ImageEnhance, ImageFilter, ImageOps
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(2.0)
    return image.filter(ImageFilter.SHARPEN)


def pixmap_to_png_bytes(pix: fitz.Pixmap) -> bytes:
    return pix.tobytes("png")


def page_thumbnail(page: fitz.Page, width: int = 190) -> bytes:
    rect = page.rect
    scale = min(1.5, max(0.35, width / max(rect.width, 1)))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pixmap_to_png_bytes(pix)


def render_for_ocr(page: fitz.Page) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")


class AnalysisWorker(QObject):
    progress = Signal(int, str)
    page_ready = Signal(object)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, files: list[str], use_ocr: bool, document_mode: str = "serial", category_rules: list[tuple[str, list[str]]] | None = None, fallback_category: str = "Resto de fallas"):

        super().__init__()
        self.files = files
        self.use_ocr = use_ocr
        self.document_mode = document_mode
        self.category_rules = category_rules or []
        self.fallback_category = fallback_category
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            total_pages = 0
            documents: list[tuple[str, int]] = []
            for filename in self.files:
                with fitz.open(filename) as document:
                    count = len(document)
                total_pages += count
                documents.append((filename, count))

            completed = 0
            for filename, page_count in documents:
                if self.cancelled:
                    break

                with fitz.open(filename) as document:
                    for page_index in range(page_count):
                        if self.cancelled:
                            break

                        page = document[page_index]
                        base_status = (
                            f"{Path(filename).name} · página {page_index + 1} de {page_count}"
                        )
                        self.progress.emit(
                            int((completed / max(total_pages, 1)) * 100),
                            f"Extrayendo texto: {base_status}",
                        )

                        direct_text = page.get_text("text") or ""
                        extractor = extract_service_report if self.document_mode == "service" else extract_serial
                        serial, confidence = extractor(direct_text)
                        missing_label = "Sin folio" if self.document_mode == "service" else "Sin identificador"
                        method = "Texto" if serial else missing_label
                        combined_text = direct_text
                        header_ocr_text = ""

                        if not serial and self.use_ocr:
                            if pytesseract is None:
                                method = "OCR no disponible"
                            else:
                                self.progress.emit(
                                    int((completed / max(total_pages, 1)) * 100),
                                    f"Aplicando OCR: {base_status}",
                                )
                                image = (
                                    render_service_header_for_ocr(page)
                                    if self.document_mode == "service"
                                    else render_for_ocr(page)
                                )
                                texts = []
                                configs = ["--psm 6", "--psm 11", "--psm 12"] if self.document_mode == "service" else ["--psm 6"]
                                for config in configs:
                                    try:
                                        texts.append(pytesseract.image_to_string(image, lang="spa+eng", config=config))
                                    except Exception:
                                        try:
                                            texts.append(pytesseract.image_to_string(image, config=config))
                                        except Exception:
                                            pass
                                header_ocr_text = "\n".join(texts)
                                combined_text = header_ocr_text
                                serial, confidence = extractor(header_ocr_text)
                                method = "OCR" if serial else missing_label

                        report_date = ""
                        report_date_confidence = 0
                        if self.document_mode == "service":
                            report_date, report_date_confidence = extract_provider_report_date(direct_text)
                            if not report_date and header_ocr_text:
                                report_date, report_date_confidence = extract_provider_report_date(
                                    header_ocr_text
                                )
                            if not report_date and self.use_ocr and pytesseract is not None:
                                self.progress.emit(
                                    int((completed / max(total_pages, 1)) * 100),
                                    f"Leyendo fecha del reporte: {base_status}",
                                )
                                try:
                                    date_image = render_service_date_for_ocr(page)
                                    date_texts = []
                                    for config in ("--psm 6", "--psm 7", "--psm 11"):
                                        try:
                                            date_texts.append(
                                                pytesseract.image_to_string(date_image, lang="spa+eng", config=config)
                                            )
                                        except Exception:
                                            try:
                                                date_texts.append(
                                                    pytesseract.image_to_string(date_image, config=config)
                                                )
                                            except Exception:
                                                pass
                                    date_ocr_text = "\n".join(date_texts)
                                    report_date, report_date_confidence = extract_provider_report_date(
                                        date_ocr_text
                                    )
                                    if date_ocr_text.strip():
                                        combined_text += "\n" + date_ocr_text

                                    if not report_date:
                                        value_image = render_service_date_for_ocr(page, value_only=True)
                                        value_texts = []
                                        for config in ("--psm 7", "--psm 11"):
                                            try:
                                                value_texts.append(
                                                    pytesseract.image_to_string(
                                                        value_image, lang="spa+eng", config=config
                                                    )
                                                )
                                            except Exception:
                                                try:
                                                    value_texts.append(
                                                        pytesseract.image_to_string(value_image, config=config)
                                                    )
                                                except Exception:
                                                    pass
                                        value_ocr_text = "\n".join(value_texts)
                                        report_date, report_date_confidence = extract_provider_report_date(
                                            value_ocr_text, allow_unlabeled=True
                                        )
                                        if value_ocr_text.strip():
                                            combined_text += "\n" + value_ocr_text
                                except Exception:
                                    pass

                        category = ""
                        category_confidence = 0
                        classification_text = combined_text
                        if self.document_mode == "service" and self.category_rules:
                            # Digital PDFs usually expose the full form text directly. For scanned
                            # certificates, OCR the failure-description area even when the folio was
                            # already found in the header.
                            if self.use_ocr and pytesseract is not None and len(direct_text.strip()) < 80:
                                try:
                                    failure_image = render_service_failure_for_ocr(page)
                                    failure_texts = []
                                    for config in ("--psm 6", "--psm 11"):
                                        try:
                                            failure_texts.append(pytesseract.image_to_string(failure_image, lang="spa+eng", config=config))
                                        except Exception:
                                            try:
                                                failure_texts.append(pytesseract.image_to_string(failure_image, config=config))
                                            except Exception:
                                                pass
                                    classification_text += "\n" + "\n".join(failure_texts)
                                except Exception:
                                    pass
                            category, category_confidence = classify_service_text(
                                classification_text, self.category_rules, self.fallback_category
                            )

                        preview = " ".join(classification_text.split())[:420]
                        thumbnail = page_thumbnail(page)

                        result = PageResult(
                            source_path=filename,
                            source_name=Path(filename).name,
                            page_index=page_index,
                            page_number=page_index + 1,
                            serial=serial,
                            method=method,
                            confidence=confidence,
                            preview_text=preview,
                            thumbnail_png=thumbnail,
                            category=category,
                            category_confidence=category_confidence,
                            report_date=report_date,
                            report_date_confidence=report_date_confidence,
                        )
                        self.page_ready.emit(result)
                        completed += 1
                        self.progress.emit(
                            int((completed / max(total_pages, 1)) * 100),
                            f"Procesada: {base_status}",
                        )

            self.finished.emit()
        except Exception as error:
            self.failed.emit(str(error))


class DropZone(QFrame):
    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("nativeDropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Selecciona o arrastra aquí uno o varios PDF")
        self.title.setObjectName("dropTitle")
        self.subtitle = QLabel("No se ha seleccionado ningún archivo.")
        self.subtitle.setObjectName("dropSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls()
        if any(url.toLocalFile().lower().endswith(".pdf") for url in urls):
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(".pdf")
        ]
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()


class ServiceIdentifierLineEdit(QLineEdit):
    """Service folio field that inserts the DGTI hyphen while typing."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMaxLength(40)
        self.textEdited.connect(self._apply_identifier_format)

    @staticmethod
    def _cursor_after_alphanumeric(value: str, character_count: int) -> int:
        if character_count <= 0:
            return 0
        seen = 0
        for position, character in enumerate(value, start=1):
            if character.isalnum():
                seen += 1
                if seen >= character_count:
                    return position
        return len(value)

    def _apply_identifier_format(self, value: str):
        cursor = self.cursorPosition()
        characters_before_cursor = sum(
            character.isalnum() for character in value[:cursor]
        )
        formatted = format_manual_service_identifier_input(value)
        if formatted == value:
            return
        self.blockSignals(True)
        self.setText(formatted)
        self.setCursorPosition(
            self._cursor_after_alphanumeric(formatted, characters_before_cursor)
        )
        self.blockSignals(False)


class ReportDateLineEdit(QLineEdit):
    """Date field that inserts DD-MM-YYYY separators while the user types."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMaxLength(10)
        self.textEdited.connect(self._apply_date_format)

    @staticmethod
    def _cursor_after_digits(value: str, digit_count: int) -> int:
        if digit_count <= 0:
            return 0
        seen = 0
        for position, character in enumerate(value, start=1):
            if character.isdigit():
                seen += 1
                if seen >= digit_count:
                    return position
        return len(value)

    def _apply_date_format(self, value: str):
        cursor = self.cursorPosition()
        digits_before_cursor = sum(character.isdigit() for character in value[:cursor])
        formatted = format_manual_report_date_input(value)
        if formatted == value:
            return
        self.blockSignals(True)
        self.setText(formatted)
        self.setCursorPosition(
            self._cursor_after_digits(formatted, digits_before_cursor)
        )
        self.blockSignals(False)


class MetricCard(QFrame):
    def __init__(self, label: str):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.value = QLabel("0")
        self.value.setObjectName("metricValue")
        text = QLabel(label)
        text.setObjectName("metricLabel")
        layout.addWidget(self.value)
        layout.addWidget(text)


class ReviewDialog(QDialog):
    def __init__(
        self,
        page: "PdfPage",
        row: int,
        mode: str = "all",
        target_rows: list[int] | None = None,
    ):
        super().__init__(page)
        self.page = page
        self.mode = mode
        self.target_rows = target_rows or list(range(len(page.results)))
        if row not in self.target_rows:
            self.target_rows.insert(0, row)
        self.position = self.target_rows.index(row)
        self.row = row
        self.source_pixmap = QPixmap()
        self.zoom = 1.0
        self.rotation_degrees = 0

        self.setWindowTitle("Examinar página y corregir identificador")
        self.setMinimumSize(1000, 700)

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.previous_button = QPushButton("← Anterior")
        self.next_button = QPushButton("Siguiente →")
        self.rotate_button = QPushButton("↻ Girar 90°")
        self.rotate_button.setToolTip("Gira la vista de la página 90° a la derecha.")
        self.fit_button = QPushButton("Ajustar al ancho")
        self.zoom_out = QPushButton("−")
        self.zoom_in = QPushButton("+")
        self.zoom_label = QLabel("100 %")
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.next_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.rotate_button)
        toolbar.addWidget(self.fit_button)
        toolbar.addWidget(self.zoom_out)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(self.zoom_in)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.scroll.setWidget(self.image_label)
        body.addWidget(self.scroll, 1)

        sidebar = QFrame()
        sidebar.setObjectName("reviewSidebar")
        side_layout = QVBoxLayout(sidebar)
        side_layout.addWidget(QLabel("Número de serie / folio de servicio"))
        self.serial_edit = (
            ServiceIdentifierLineEdit()
            if page.document_mode.currentData() == "service"
            else QLineEdit()
        )
        self.serial_edit.setObjectName("serialEditor")
        if page.document_mode.currentData() == "service":
            self.serial_edit.setPlaceholderText("R-015422 o R015422")
            self.serial_edit.setToolTip(
                "Escribe R015422 y Atlas insertará automáticamente el guion: R-015422. "
                "Cada folio debe ser único durante la sesión actual."
            )
        else:
            self.serial_edit.setPlaceholderText("Escribe o corrige el número de serie")
        side_layout.addWidget(self.serial_edit)

        self.category_label = QLabel("Categoría de exportación")
        self.category_combo = QComboBox()
        categories = [name for name, _ in page.service_category_rules]
        if page.service_fallback_category:
            categories.append(page.service_fallback_category)
        self.category_combo.addItems(list(dict.fromkeys(categories)))
        self.category_label.setVisible(page.document_mode.currentData() == "service")
        self.category_combo.setVisible(page.document_mode.currentData() == "service")
        side_layout.addWidget(self.category_label)
        side_layout.addWidget(self.category_combo)

        self.report_date_label = QLabel("Fecha reporte del prestador de servicio")
        self.report_date_edit = ReportDateLineEdit()
        self.report_date_edit.setPlaceholderText("DD-MM-AAAA o DDMMAAAA")
        self.report_date_edit.setToolTip(
            "Escribe 09072026 o 09-07-2026. Esta fecha determina la carpeta mensual de exportación."
        )
        self.report_date_label.setVisible(page.document_mode.currentData() == "service")
        self.report_date_edit.setVisible(page.document_mode.currentData() == "service")
        side_layout.addWidget(self.report_date_label)
        side_layout.addWidget(self.report_date_edit)

        self.page_info = QLabel()
        self.page_info.setWordWrap(True)
        self.method_info = QLabel()
        self.method_info.setWordWrap(True)
        side_layout.addWidget(self.page_info)
        side_layout.addWidget(self.method_info)

        if self.mode == "duplicates":
            next_text = "Guardar y abrir siguiente repetida"
            help_text = (
                "Presiona Enter para guardar y abrir la siguiente entrada repetida. "
                "Al terminar se guardará y cerrará."
            )
        elif self.mode == "missing":
            next_text = "Guardar y abrir siguiente sin identificador"
            help_text = (
                "Presiona Enter para guardar y abrir la siguiente entrada sin identificador. "
                "Si ya no quedan entradas pendientes, se guardará y cerrará."
            )
        else:
            next_text = "Guardar y abrir siguiente"
            help_text = (
                "Presiona Enter para guardar y abrir la siguiente entrada de esta revisión. "
                "Al terminar se guardará y cerrará."
            )

        self.save_next = QPushButton(next_text)
        self.save_next.setObjectName("primaryButton")
        self.save_close = QPushButton("Guardar y cerrar")
        self.delete_button = QPushButton("🗑️ Eliminar entrada")
        self.delete_button.setObjectName("dangerButton")
        side_layout.addWidget(self.save_next)
        side_layout.addWidget(self.save_close)
        side_layout.addWidget(self.delete_button)

        help_text += " Usa las flechas ↑ y ↓ para cambiar entre los campos editables."
        help_label = QLabel(help_text)
        help_label.setObjectName("reviewHelp")
        help_label.setWordWrap(True)
        side_layout.addWidget(help_label)

        side_layout.addWidget(QLabel("Texto detectado"))
        self.detected_text = QLabel()
        self.detected_text.setObjectName("detectedText")
        self.detected_text.setWordWrap(True)
        self.detected_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        side_layout.addWidget(self.detected_text, 1)
        body.addWidget(sidebar)
        root.addLayout(body, 1)

        self.previous_button.clicked.connect(lambda: self.move_position(-1))
        self.next_button.clicked.connect(lambda: self.move_position(1))
        self.rotate_button.clicked.connect(self.rotate_clockwise)
        self.fit_button.clicked.connect(self.fit_to_width)
        self.zoom_out.clicked.connect(lambda: self.change_zoom(-0.15))
        self.zoom_in.clicked.connect(lambda: self.change_zoom(0.15))
        self.save_next.clicked.connect(self.save_and_next)
        self.save_close.clicked.connect(self.save_and_close)
        self.delete_button.clicked.connect(self.delete_current)
        self.serial_edit.returnPressed.connect(self.save_and_next)

        self.editable_fields = [
            self.serial_edit,
            self.category_combo,
            self.report_date_edit,
        ]
        for field in self.editable_fields:
            field.installEventFilter(self)

        # Open nearly full screen so the page is readable immediately.
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                max(1000, int(available.width() * 0.96)),
                max(700, int(available.height() * 0.94)),
            )
            self.move(
                available.x() + max(0, (available.width() - self.width()) // 2),
                available.y() + max(0, (available.height() - self.height()) // 2),
            )

        self.load_row(row)
        QTimer.singleShot(0, self.fit_to_width)

    def current_result(self) -> PageResult:
        return self.page.results[self.row]

    def render_source_page(self) -> QPixmap:
        result = self.current_result()
        try:
            with fitz.open(result.source_path) as document:
                page = document[result.page_index]
                # Render at high resolution once. Zooming uses this source rather
                # than the tiny table thumbnail, so text stays sharp.
                target_width = 2400
                scale = max(2.0, target_width / max(page.rect.width, 1))
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    alpha=False,
                )
                pixmap = QPixmap()
                pixmap.loadFromData(pix.tobytes("png"), "PNG")
                return pixmap
        except Exception:
            # Emergency fallback: use the existing thumbnail.
            pixmap = QPixmap()
            pixmap.loadFromData(result.thumbnail_png, "PNG")
            return pixmap

    def load_row(self, row: int):
        if not self.page.results:
            self.close()
            return

        self.row = max(0, min(row, len(self.page.results) - 1))
        if self.row in self.target_rows:
            self.position = self.target_rows.index(self.row)

        result = self.current_result()
        self.serial_edit.setText(result.serial)
        if self.page.document_mode.currentData() == "service":
            if result.category and self.category_combo.findText(result.category) < 0:
                self.category_combo.addItem(result.category)
            self.category_combo.setCurrentText(result.category or self.page.service_fallback_category)
            self.report_date_edit.setText(display_report_date(result.report_date))

        review_label = ""
        if self.mode == "duplicates":
            review_label = (
                f"<br><b>Entrada repetida {self.position + 1} "
                f"de {len(self.target_rows)}</b>"
            )
        elif self.mode == "missing":
            review_label = (
                f"<br><b>Entrada sin identificador {self.position + 1} "
                f"de {len(self.target_rows)}</b>"
            )

        self.page_info.setText(
            f"<b>{result.source_name}</b><br>Página {result.page_number}"
            f"{review_label}"
        )
        self.method_info.setText(
            f"Método: {result.method} · Confianza: {result.confidence}%"
        )
        self.detected_text.setText(
            result.preview_text or "Sin texto reconocible."
        )

        self.rotation_degrees = 0
        self.source_pixmap = self.render_source_page()
        self.fit_to_width()
        self.update_navigation_buttons()

        self.serial_edit.setFocus()
        self.serial_edit.selectAll()

    def update_navigation_buttons(self):
        self.previous_button.setEnabled(self.position > 0)
        self.next_button.setEnabled(
            self.position < len(self.target_rows) - 1
        )

    def display_pixmap(self) -> QPixmap:
        if self.source_pixmap.isNull() or self.rotation_degrees % 360 == 0:
            return self.source_pixmap
        return self.source_pixmap.transformed(
            QTransform().rotate(self.rotation_degrees),
            Qt.TransformationMode.SmoothTransformation,
        )

    def update_image(self):
        display_pixmap = self.display_pixmap()
        if display_pixmap.isNull():
            return

        scaled_size = display_pixmap.size() * self.zoom
        scaled = display_pixmap.scaled(
            scaled_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.zoom_label.setText(f"{int(self.zoom * 100)} %")

    def fit_to_width(self):
        display_pixmap = self.display_pixmap()
        if display_pixmap.isNull():
            return

        viewport_width = max(320, self.scroll.viewport().width() - 28)
        self.zoom = max(
            0.20,
            min(1.25, viewport_width / max(display_pixmap.width(), 1)),
        )
        self.update_image()

    def rotate_clockwise(self):
        self.rotation_degrees = (self.rotation_degrees + 90) % 360
        self.fit_to_width()

    def visible_editable_fields(self) -> list[QWidget]:
        return [
            field
            for field in self.editable_fields
            if field.isVisible() and field.isEnabled()
        ]

    def focus_adjacent_field(self, delta: int):
        fields = self.visible_editable_fields()
        if not fields:
            return
        current = QApplication.focusWidget()
        try:
            index = fields.index(current)
        except ValueError:
            index = 0 if delta >= 0 else len(fields) - 1
        else:
            index = (index + delta) % len(fields)
        target = fields[index]
        target.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if isinstance(target, QLineEdit):
            target.selectAll()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in self.editable_fields and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self.focus_adjacent_field(-1)
                return True
            if key == Qt.Key.Key_Down:
                self.focus_adjacent_field(1)
                return True
        return super().eventFilter(watched, event)

    def change_zoom(self, delta: float):
        self.zoom = max(0.20, min(2.5, self.zoom + delta))
        self.update_image()

    def save_current(self) -> bool:
        serial = (
            normalize_service_identifier(self.serial_edit.text())
            if self.page.document_mode.currentData() == "service"
            else normalize_serial(self.serial_edit.text())
        )
        result = self.current_result()
        duplicate_row = self.page.session_duplicate_row(self.row, serial)
        if duplicate_row is not None:
            QMessageBox.warning(
                self,
                "Folio duplicado en esta sesión",
                self.page.session_duplicate_message(serial, duplicate_row),
            )
            self.serial_edit.setFocus()
            self.serial_edit.selectAll()
            return False

        result.serial = serial
        if self.page.document_mode.currentData() == "service":
            raw_date = self.report_date_edit.text().strip()
            parsed_date = parse_manual_report_date(raw_date) if raw_date else ""
            if raw_date and not parsed_date:
                QMessageBox.warning(
                    self,
                    "Fecha no válida",
                    "Escribe la fecha del reporte con formato DD-MM-AAAA, por ejemplo 30-07-2026.",
                )
                self.report_date_edit.setFocus()
                self.report_date_edit.selectAll()
                return False
            result.category = self.category_combo.currentText().strip()
            result.category_confidence = 100
            result.report_date = parsed_date
            result.report_date_confidence = 100 if parsed_date else 0

        if serial and result.method.startswith("Sin "):
            result.method = "Manual"
            result.confidence = 100

        self.page.refresh_row(self.row)
        self.page.update_metrics()
        return True

    def move_position(self, delta: int):
        if not self.save_current():
            return
        new_position = self.position + delta
        if 0 <= new_position < len(self.target_rows):
            self.position = new_position
            self.load_row(self.target_rows[self.position])

    def save_and_next(self):
        if not self.save_current():
            return
        if self.position + 1 < len(self.target_rows):
            self.position += 1
            self.load_row(self.target_rows[self.position])
            return
        self.accept()

    def save_and_close(self):
        if self.save_current():
            self.accept()

    def delete_current(self):
        """Delete the current review entry and continue when more remain.

        The review dialog should behave like ``save_and_next``: removing one
        item must not interrupt the review session.  Remove the current row
        from this dialog's review queue, refresh the parent table and load the
        next pending item at the same queue position.  Close only when the
        deleted item was the last pending entry.
        """
        self.current_result().deleted = True
        self.page.rebuild_table()
        self.page.update_metrics()

        # ``target_rows`` stores indexes into ``page.results``.  The results
        # list itself is not compacted when an entry is marked deleted, so it
        # is safe to remove only the current index from the review queue.
        if 0 <= self.position < len(self.target_rows):
            self.target_rows.pop(self.position)

        if self.position < len(self.target_rows):
            self.load_row(self.target_rows[self.position])
            return

        self.accept()

class ServiceCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clasificación de cédulas para esta sesión")
        self.resize(760, 520)
        root = QVBoxLayout(self)
        intro = QLabel(
            "Define las carpetas que deseas separar en esta sesión. Escribe una categoría por fila "
            "y sus palabras clave separadas por comas. Todo lo que no coincida irá a la categoría general. "
            "Además, cada cédula se organizará por el mes de la fecha del reporte del prestador de servicio."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Categoría", "Palabras clave (separadas por comas)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        add_button = QPushButton("+ Añadir categoría")
        remove_button = QPushButton("Eliminar seleccionada")
        defaults_button = QPushButton("Restaurar Tóner / Resto")
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addWidget(defaults_button)
        actions.addStretch(1)
        root.addLayout(actions)

        fallback_row = QHBoxLayout()
        fallback_row.addWidget(QLabel("Categoría para lo que no coincida:"))
        self.fallback_edit = QLineEdit("Resto de fallas")
        fallback_row.addWidget(self.fallback_edit, 1)
        root.addLayout(fallback_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        root.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        add_button.clicked.connect(self.add_empty_row)
        remove_button.clicked.connect(self.remove_selected_row)
        defaults_button.clicked.connect(self.load_defaults)
        self.load_defaults()

    def load_defaults(self):
        self.table.setRowCount(0)
        self.add_rule(
            "Tóner",
            "tóner, toner, cartucho, consumible, cambio de tóner, reemplazo de tóner, sustituir tóner, suministro de tóner"
        )
        self.fallback_edit.setText("Resto de fallas")

    def add_rule(self, category: str, keywords: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(category))
        self.table.setItem(row, 1, QTableWidgetItem(keywords))

    def add_empty_row(self):
        self.add_rule("Nueva categoría", "")
        self.table.editItem(self.table.item(self.table.rowCount() - 1, 0))

    def remove_selected_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def values(self) -> tuple[list[tuple[str, list[str]]], str]:
        rules = []
        for row in range(self.table.rowCount()):
            category_item = self.table.item(row, 0)
            keywords_item = self.table.item(row, 1)
            category = category_item.text().strip() if category_item else ""
            keywords = [part.strip() for part in (keywords_item.text() if keywords_item else "").split(",") if part.strip()]
            if category and keywords:
                rules.append((category, keywords))
        fallback = self.fallback_edit.text().strip() or "Resto de fallas"
        return rules, fallback


class ExportHistoryDialog(QDialog):
    """Show the persistent local history of PDF separator exports."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Historial del separador inteligente")
        self.resize(1050, 560)

        root = QVBoxLayout(self)
        title = QLabel("Historial de exportaciones")
        title.setObjectName("nativeSectionTitle")
        intro = QLabel(
            "Atlas guarda únicamente los metadatos de cada exportación. "
            "No conserva copias adicionales de los PDF procesados."
        )
        intro.setWordWrap(True)
        intro.setObjectName("nativeModuleSubtitle")
        root.addWidget(title)
        root.addWidget(intro)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Fecha y hora",
            "Tipo",
            "Archivo ZIP",
            "Archivos origen",
            "Páginas",
            "Identificados",
            "Categorías",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.location_label = QLabel()
        self.location_label.setWordWrap(True)
        self.location_label.setObjectName("nativeModuleSubtitle")
        root.addWidget(self.location_label)

        actions = QHBoxLayout()
        refresh_button = QPushButton("Actualizar")
        refresh_button.setObjectName("secondaryButton")
        clear_button = QPushButton("Borrar historial")
        clear_button.setObjectName("dangerButton")
        close_button = QPushButton("Cerrar")
        close_button.setObjectName("primaryButton")
        actions.addWidget(refresh_button)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        actions.addWidget(close_button)
        root.addLayout(actions)

        refresh_button.clicked.connect(self.reload)
        clear_button.clicked.connect(self.clear_history)
        close_button.clicked.connect(self.accept)
        self.reload()

    @staticmethod
    def _display_timestamp(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.strftime("%d-%m-%Y %H:%M:%S")
        except ValueError:
            return raw

    @staticmethod
    def _as_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _category_summary(value: object) -> str:
        if not isinstance(value, dict):
            return ""
        parts = [
            f"{name}: {count}"
            for name, count in sorted(value.items(), key=lambda item: str(item[0]).casefold())
        ]
        return ", ".join(parts)

    def reload(self):
        records = list(reversed(load_export_history()))
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            source_files = record.get("source_files", [])
            if not isinstance(source_files, list):
                source_files = []
            source_count = self._as_int(
                record.get("source_file_count", len(source_files)),
                len(source_files),
            )
            identified = self._as_int(record.get("identified_count", 0))
            provisional = self._as_int(record.get("provisional_count", 0))
            identified_text = str(identified)
            if provisional:
                identified_text += f" (+{provisional} provisional)"

            values = [
                self._display_timestamp(record.get("exported_at")),
                str(record.get("document_type", "")),
                str(record.get("output_zip", "")),
                str(source_count),
                str(record.get("page_count", 0)),
                identified_text,
                self._category_summary(record.get("categories")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setToolTip(str(record.get("output_zip", "")))
                elif column == 3:
                    item.setToolTip("\n".join(str(item) for item in source_files))
                self.table.setItem(row, column, item)

        history_file = separator_history_path()
        self.location_label.setText(
            f"Registros guardados: {len(records)} · Archivo local: {history_file}"
        )
        self.table.resizeRowsToContents()

    def clear_history(self):
        if not load_export_history():
            return
        answer = QMessageBox.question(
            self,
            "Borrar historial",
            "¿Deseas eliminar todo el historial del separador inteligente? "
            "Los archivos ZIP exportados no serán eliminados.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_export_history()
        except OSError as error:
            QMessageBox.critical(
                self,
                "No se pudo borrar el historial",
                str(error),
            )
            return
        self.reload()


class PdfPage(QWidget):
    def __init__(self):
        super().__init__()
        self.files: list[str] = []
        self.results: list[PageResult] = []
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.service_category_rules: list[tuple[str, list[str]]] = []
        self.service_fallback_category = "Resto de fallas"
        self.session_duplicate_rejections = 0

        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("nativeModuleBackground")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 42)
        root.setSpacing(18)

        title = QLabel("Separador inteligente de PDF")
        title.setObjectName("nativeModuleTitle")
        subtitle = QLabel(
            "Analiza uno o varios PDF, busca el número de serie o el folio de servicio en cada hoja y genera un archivo ZIP "
            "con cada página convertida en un PDF independiente. Antes de exportar puedes corregir "
            "cualquier identificador manualmente."
        )
        subtitle.setObjectName("nativeModuleSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("nativePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(15)

        self.drop_zone = DropZone()
        self.drop_zone.clicked.connect(self.choose_files)
        self.drop_zone.files_dropped.connect(self.set_files)
        panel_layout.addWidget(self.drop_zone)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Tipo de documento:")
        self.document_mode = QComboBox()
        self.document_mode.addItem("Equipos — separar por número de serie", "serial")
        self.document_mode.addItem("Cédulas de servicio — separar por folio/reporte", "service")
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.document_mode, 1)
        panel_layout.addLayout(mode_row)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.folder_button = QPushButton("Examinar carpeta completa")
        self.folder_button.setObjectName("secondaryButton")
        self.analyze_button = QPushButton("Analizar páginas")
        self.analyze_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("dangerButton")
        self.export_button = QPushButton("Exportar ZIP y elegir ubicación")
        self.export_button.setObjectName("secondaryButton")
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.setObjectName("secondaryButton")
        self.history_button = QPushButton("Historial")
        self.history_button.setObjectName("secondaryButton")
        controls.addWidget(self.folder_button)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.export_button)
        controls.addWidget(self.clear_button)
        controls.addWidget(self.history_button)
        controls.addStretch(1)
        panel_layout.addLayout(controls)

        options = QHBoxLayout()
        self.ocr_checkbox = QCheckBox("Usar OCR cuando el PDF no tenga texto reconocible")
        self.ocr_checkbox.setChecked(True)
        self.native_badge = QLabel("Motor nativo Python · procesamiento local")
        self.native_badge.setObjectName("nativeBadge")
        options.addWidget(self.ocr_checkbox)
        options.addStretch(1)
        options.addWidget(self.native_badge)
        panel_layout.addLayout(options)

        self.note = QLabel(
            "El motor nativo usa texto directo cuando existe y aplica OCR únicamente a las páginas "
            "escaneadas. Los documentos permanecen en esta computadora."
        )
        self.note.setObjectName("nativeNote")
        self.note.setWordWrap(True)
        panel_layout.addWidget(self.note)

        status_row = QHBoxLayout()
        self.status_text = QLabel("Esperando uno o varios PDF.")
        self.progress_text = QLabel("0%")
        self.progress_text.setObjectName("progressPercent")
        status_row.addWidget(self.status_text)
        status_row.addStretch(1)
        status_row.addWidget(self.progress_text)
        panel_layout.addLayout(status_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        panel_layout.addWidget(self.progress_bar)

        metrics = QGridLayout()
        metrics.setSpacing(12)
        self.metric_pages = MetricCard("Páginas")
        self.metric_found = MetricCard("Identificadores detectados")
        self.metric_missing = MetricCard("Sin identificador")
        self.metric_duplicates = MetricCard("Identificadores repetidos")
        metrics.addWidget(self.metric_pages, 0, 0)
        metrics.addWidget(self.metric_found, 0, 1)
        metrics.addWidget(self.metric_missing, 0, 2)
        metrics.addWidget(self.metric_duplicates, 0, 3)
        panel_layout.addLayout(metrics)

        self.notice = QLabel("")
        self.notice.setObjectName("nativeNotice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        panel_layout.addWidget(self.notice)
        root.addWidget(panel)

        self.results_panel = QFrame()
        self.results_panel.setObjectName("nativePanel")
        results_layout = QVBoxLayout(self.results_panel)
        results_layout.setContentsMargins(20, 18, 20, 20)

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        h2 = QLabel("Revisión antes de exportar")
        h2.setObjectName("nativeSectionTitle")
        h2_subtitle = QLabel(
            "Corrige los identificadores incompletos o mal reconocidos. Haz doble clic en una fila "
            "para examinar la página completa."
        )
        h2_subtitle.setObjectName("nativeModuleSubtitle")
        h2_subtitle.setWordWrap(True)
        header_text.addWidget(h2)
        header_text.addWidget(h2_subtitle)
        header.addLayout(header_text)
        header.addStretch(1)
        self.review_missing_button = QPushButton("Examinar siguiente sin identificador")
        self.review_missing_button.setObjectName("secondaryButton")
        self.review_duplicates_button = QPushButton("Examinar identificadores repetidos")
        self.review_duplicates_button.setObjectName("duplicateReviewButton")
        header.addWidget(self.review_missing_button)
        header.addWidget(self.review_duplicates_button)
        results_layout.addLayout(header)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "PDF", "Página", "Vista previa", "Serie / folio",
            "Método", "Confianza OCR", "Categoría", "Fecha reporte",
            "Texto detectado", ""
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.table.setMinimumHeight(220)
        results_layout.addWidget(self.table)
        self.results_panel.hide()
        root.addWidget(self.results_panel)

        footer = QLabel(
            "El separador no transmite los documentos ni conserva copias adicionales. "
            "El historial local guarda solamente los datos de cada exportación y la ruta del ZIP."
        )
        footer.setObjectName("nativeModuleSubtitle")
        footer.setWordWrap(True)
        root.addWidget(footer)

        self.folder_button.clicked.connect(self.choose_folder)
        self.analyze_button.clicked.connect(self.start_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.export_button.clicked.connect(self.export_zip)
        self.clear_button.clicked.connect(self.clear_all)
        self.history_button.clicked.connect(self.show_export_history)
        self.review_missing_button.clicked.connect(self.review_next_missing)
        self.review_duplicates_button.clicked.connect(self.review_duplicates)
        self.table.cellDoubleClicked.connect(
            lambda row, column: self.open_review(row, mode="all")
        )

        self.document_mode.currentIndexChanged.connect(self.update_document_mode_labels)
        self.update_document_mode_labels()
        self.set_controls_state()


    def update_document_mode_labels(self):
        service = self.document_mode.currentData() == "service"
        if service:
            self.drop_zone.title.setText("Selecciona o arrastra PDF con cédulas de servicio")
            self.ocr_checkbox.setText("Usar OCR para texto impreso o manuscrito cuando sea necesario")
            self.note.setText(
                "Se buscará primero el reporte asignado por el prestador de servicio (por ejemplo, REQ...) y "
                "la fecha del reporte del prestador de servicio. Esa fecha determina la carpeta mensual. "
                "La letra manuscrita se procesa localmente como mejor esfuerzo y puede corregirse antes de exportar."
            )
            self.metric_found.findChild(QLabel, "metricLabel")
        else:
            self.drop_zone.title.setText("Selecciona o arrastra aquí uno o varios PDF")
            self.ocr_checkbox.setText("Usar OCR cuando el PDF no tenga texto reconocible")
            self.note.setText(
                "El motor nativo usa texto directo cuando existe y aplica OCR únicamente a las páginas "
                "escaneadas. Los documentos permanecen en esta computadora."
            )

    def set_controls_state(self, running: bool = False):
        self.analyze_button.setEnabled(bool(self.files) and not running)
        self.cancel_button.setEnabled(running)
        self.export_button.setEnabled(
            bool([result for result in self.results if not result.deleted]) and not running
        )
        self.clear_button.setEnabled(not running)
        self.folder_button.setEnabled(not running)
        self.history_button.setEnabled(not running)
        self.drop_zone.setEnabled(not running)

    def show_export_history(self):
        ExportHistoryDialog(self).exec()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar uno o varios PDF",
            "",
            "Documentos PDF (*.pdf)",
        )
        if files:
            self.set_files(files)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta con documentos PDF",
        )
        if not folder:
            return
        files = sorted(
            str(path)
            for path in Path(folder).rglob("*.pdf")
            if path.is_file()
        )
        if not files:
            QMessageBox.information(
                self,
                "Carpeta sin PDF",
                "No se encontraron documentos PDF en la carpeta seleccionada.",
            )
            return
        self.set_files(files)

    def set_files(self, files: list[str]):
        clean = []
        seen = set()
        for filename in files:
            path = str(Path(filename).resolve())
            if path.lower().endswith(".pdf") and path not in seen:
                clean.append(path)
                seen.add(path)
        self.files = clean
        self.results.clear()
        self.session_duplicate_rejections = 0
        self.rebuild_table()
        self.update_metrics()
        self.results_panel.hide()

        if len(clean) == 1:
            label = Path(clean[0]).name
        else:
            label = f"{len(clean)} PDF seleccionados"
        self.drop_zone.subtitle.setText(label)
        self.status_text.setText("Listo para analizar.")
        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.notice.hide()
        self.set_controls_state()

    def start_analysis(self):
        if not self.files:
            return
        if self.document_mode.currentData() == "service":
            dialog = ServiceCategoryDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.service_category_rules, self.service_fallback_category = dialog.values()
            if not self.service_category_rules:
                QMessageBox.warning(
                    self,
                    "Sin categorías configuradas",
                    "Añade al menos una categoría con palabras clave para iniciar la clasificación.",
                )
                return
        else:
            self.service_category_rules = []
            self.service_fallback_category = ""
        self.results.clear()
        self.session_duplicate_rejections = 0
        self.rebuild_table()
        self.update_metrics()
        self.results_panel.show()
        self.notice.hide()
        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.set_controls_state(running=True)

        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(
            self.files,
            self.ocr_checkbox.isChecked(),
            self.document_mode.currentData(),
            self.service_category_rules,
            self.service_fallback_category,
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.page_ready.connect(self.on_page_ready)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def cancel_analysis(self):
        if self.worker:
            self.worker.cancel()
            self.status_text.setText("Cancelando después de la página actual…")
            self.cancel_button.setEnabled(False)

    def on_progress(self, value: int, text: str):
        self.progress_bar.setValue(value)
        self.progress_text.setText(f"{value}%")
        self.status_text.setText(text)

    def on_page_ready(self, result: PageResult):
        if (
            self.document_mode.currentData() == "service"
            and result.serial
            and find_session_duplicate_identifier(self.results, result.serial) is not None
        ):
            # Keep the page for manual review, but never assign the same folio
            # twice inside one separator session.
            result.serial = ""
            result.method = "Sin folio (duplicado)"
            result.confidence = 0
            self.session_duplicate_rejections += 1

        self.results.append(result)
        self.append_table_row(result)
        self.update_metrics()

    def on_finished(self):
        self.progress_bar.setValue(100)
        self.progress_text.setText("100%")
        if self.worker and self.worker.cancelled:
            self.status_text.setText("Análisis cancelado. Se conservaron las páginas procesadas.")
        else:
            self.status_text.setText("Análisis terminado. Revisa los resultados antes de exportar.")
        self.set_controls_state(running=False)
        self.worker = None
        self.worker_thread = None

        if self.ocr_checkbox.isChecked() and pytesseract is None:
            self.show_notice(
                "PyTesseract no está instalado. Las páginas sin texto quedaron para revisión manual.",
                error=True,
            )
        else:
            missing = self.missing_count()
            duplicate_rows = self.duplicate_rows()

            messages = []
            if missing:
                messages.append(
                    f"Hay {missing} página(s) sin identificador."
                )
            if self.session_duplicate_rejections:
                messages.append(
                    f"Atlas rechazó {self.session_duplicate_rejections} folio(s) "
                    "repetido(s) detectado(s) en esta sesión."
                )
            if duplicate_rows:
                messages.append(
                    f"Hay {len(duplicate_rows)} entrada(s) pertenecientes "
                    "a identificadores repetidos."
                )

            if messages:
                self.show_notice(
                    " ".join(messages)
                    + " Usa los botones de revisión antes de exportar.",
                    error=False,
                )
            else:
                self.show_notice(
                    "Todas las páginas tienen un identificador único.",
                    error=False,
                )

    def on_failed(self, message: str):
        self.status_text.setText("El análisis se interrumpió.")
        self.set_controls_state(running=False)
        self.worker = None
        self.worker_thread = None
        self.show_notice(message, error=True)
        QMessageBox.critical(self, "No se pudo analizar el PDF", message)

    def show_notice(self, text: str, error: bool):
        self.notice.setText(text)
        self.notice.setProperty("error", error)
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice.show()

    def append_table_row(self, result: PageResult):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.populate_row(row, result)
        self.adjust_table_height()

    def adjust_table_height(self):
        """Use only the outer module scrollbar for vertical navigation."""
        row_count = self.table.rowCount()
        if row_count <= 0:
            self.table.setFixedHeight(220)
            return

        rows_height = sum(
            self.table.rowHeight(row)
            for row in range(row_count)
        )
        header_height = self.table.horizontalHeader().height()
        frame_height = self.table.frameWidth() * 2
        self.table.setFixedHeight(
            header_height + rows_height + frame_height + 8
        )

    def populate_row(self, row: int, result: PageResult):
        self.table.setItem(row, 0, QTableWidgetItem(result.source_name))
        self.table.setItem(row, 1, QTableWidgetItem(str(result.page_number)))

        thumbnail = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(result.thumbnail_png, "PNG")
        thumbnail.setPixmap(
            pixmap.scaled(
                72, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 2, thumbnail)
        self.table.setRowHeight(row, 108)

        if self.document_mode.currentData() == "service":
            serial_edit = ServiceIdentifierLineEdit()
            serial_edit.setText(format_manual_service_identifier_input(result.serial))
            serial_edit.setPlaceholderText("R-015422 o R015422")
            serial_edit.setToolTip(
                "Escribe R015422 y Atlas insertará automáticamente el guion: R-015422. "
                "Cada folio debe ser único durante la sesión actual."
            )
        else:
            serial_edit = QLineEdit(result.serial)
            serial_edit.setPlaceholderText("Sin identificador")
        serial_edit.setObjectName("tableSerialEditor")
        serial_edit.editingFinished.connect(
            lambda row=row, edit=serial_edit: self.update_serial(row, edit.text())
        )
        self.table.setCellWidget(row, 3, serial_edit)

        method = QLabel(result.method)
        method.setObjectName(
            "methodText" if result.method == "Texto"
            else "methodOcr" if result.method == "OCR"
            else "methodNone"
        )
        method.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 4, method)

        confidence = QLabel(f"{result.confidence}%" if result.confidence else "—")
        confidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, 5, confidence)

        category_combo = QComboBox()
        categories = [name for name, _ in self.service_category_rules]
        if self.service_fallback_category:
            categories.append(self.service_fallback_category)
        categories = list(dict.fromkeys(categories))
        if self.document_mode.currentData() == "service":
            category_combo.addItems(categories)
            if result.category and result.category not in categories:
                category_combo.addItem(result.category)
            category_combo.setCurrentText(result.category or self.service_fallback_category)
            category_combo.currentTextChanged.connect(
                lambda value, row=row: self.update_category(row, value)
            )
            category_combo.setToolTip(f"Confianza de clasificación: {result.category_confidence}%")
        else:
            category_combo.addItem("—")
            category_combo.setEnabled(False)
        self.table.setCellWidget(row, 6, category_combo)

        date_edit = ReportDateLineEdit()
        date_edit.setPlaceholderText("DD-MM-AAAA o DDMMAAAA")
        date_edit.setText(display_report_date(result.report_date))
        if self.document_mode.currentData() == "service":
            year_name, month_name = date_folder_names(result.report_date)
            confidence_text = (
                f" · confianza {result.report_date_confidence}%"
                if result.report_date_confidence
                else ""
            )
            date_edit.setToolTip(
                f"Ruta de exportación: {year_name}/{month_name}{confidence_text}. "
                "Escribe 09072026 o 09-07-2026 para corregir la fecha del reporte del prestador de servicio."
            )
            date_edit.editingFinished.connect(
                lambda row=row, edit=date_edit: self.update_report_date(row, edit.text())
            )
        else:
            date_edit.setText("—")
            date_edit.setEnabled(False)
        self.table.setCellWidget(row, 7, date_edit)

        preview = QLabel(result.preview_text or "Sin texto reconocible.")
        preview.setWordWrap(True)
        preview.setMaximumWidth(360)
        preview.setToolTip(result.preview_text)
        self.table.setCellWidget(row, 8, preview)

        delete_button = QPushButton("🗑️")
        delete_button.setToolTip("Eliminar entrada")
        delete_button.setObjectName("trashButton")
        delete_button.clicked.connect(lambda checked=False, row=row: self.delete_row(row))
        self.table.setCellWidget(row, 9, delete_button)

    def refresh_row(self, row: int):
        if 0 <= row < len(self.results):
            self.populate_row(row, self.results[row])

    def rebuild_table(self):
        self.table.setRowCount(0)
        visible_results = [result for result in self.results if not result.deleted]
        self.results = visible_results
        for result in self.results:
            self.append_table_row(result)
        self.adjust_table_height()
        self.results_panel.setVisible(bool(self.results))

    def session_duplicate_row(self, row: int, serial: str) -> int | None:
        if self.document_mode.currentData() != "service" or not serial:
            return None
        return find_session_duplicate_identifier(
            self.results,
            serial,
            exclude_row=row,
        )

    def session_duplicate_message(self, serial: str, duplicate_row: int) -> str:
        normalized = normalize_service_identifier(serial)
        existing = self.results[duplicate_row]
        return (
            f"El folio {normalized} ya está asignado a "
            f"{existing.source_name}, página {existing.page_number}.\n\n"
            "Cada folio puede aparecer una sola vez durante la sesión actual. "
            "En una sesión nueva podrá capturarse nuevamente."
        )

    def update_serial(self, row: int, value: str):
        if not (0 <= row < len(self.results)):
            return
        serial = (
            normalize_service_identifier(value)
            if self.document_mode.currentData() == "service"
            else normalize_serial(value)
        )
        duplicate_row = self.session_duplicate_row(row, serial)
        if duplicate_row is not None:
            QMessageBox.warning(
                self,
                "Folio duplicado en esta sesión",
                self.session_duplicate_message(serial, duplicate_row),
            )
            self.refresh_row(row)
            editor = self.table.cellWidget(row, 3)
            if isinstance(editor, QLineEdit):
                editor.setFocus()
                editor.selectAll()
            return

        result = self.results[row]
        result.serial = serial
        if serial and result.method.startswith("Sin "):
            result.method = "Manual"
            result.confidence = 100
            self.refresh_row(row)
        self.update_metrics()

    def update_category(self, row: int, value: str):
        if 0 <= row < len(self.results):
            self.results[row].category = value.strip()
            self.results[row].category_confidence = 100

    def update_report_date(self, row: int, value: str):
        if not (0 <= row < len(self.results)):
            return
        raw = value.strip()
        parsed = parse_manual_report_date(raw) if raw else ""
        if raw and not parsed:
            QMessageBox.warning(
                self,
                "Fecha no válida",
                "Escribe la fecha del reporte con formato DD-MM-AAAA, por ejemplo 30-07-2026.",
            )
            self.refresh_row(row)
            return
        result = self.results[row]
        result.report_date = parsed
        result.report_date_confidence = 100 if parsed else 0

    def delete_row(self, row: int):
        if not (0 <= row < len(self.results)):
            return
        self.results[row].deleted = True
        self.rebuild_table()
        self.update_metrics()
        self.set_controls_state(running=False)


    def missing_count(self) -> int:
        return sum(
            1
            for result in self.results
            if not result.deleted and not result.serial
        )

    def serial_counts(self) -> Counter:
        return Counter(
            result.serial
            for result in self.results
            if not result.deleted and result.serial
        )

    def duplicate_serials(self) -> set[str]:
        return {
            serial
            for serial, count in self.serial_counts().items()
            if count > 1
        }

    def duplicate_rows(self) -> list[int]:
        duplicates = self.duplicate_serials()
        return [
            index
            for index, result in enumerate(self.results)
            if (
                not result.deleted
                and result.serial
                and result.serial in duplicates
            )
        ]

    def refresh_duplicate_highlights(self):
        duplicates = self.duplicate_serials()
        for row, result in enumerate(self.results):
            editor = self.table.cellWidget(row, 3)
            if not isinstance(editor, QLineEdit):
                continue

            is_duplicate = bool(
                result.serial and result.serial in duplicates
            )
            editor.setProperty("duplicate", is_duplicate)
            editor.setToolTip(
                "Este identificador aparece en más de una entrada."
                if is_duplicate
                else ""
            )
            editor.style().unpolish(editor)
            editor.style().polish(editor)

    def update_metrics(self):
        active = [
            result for result in self.results if not result.deleted
        ]
        serials = [
            result.serial for result in active if result.serial
        ]
        counts = Counter(serials)
        repeated_extra_entries = sum(
            count - 1 for count in counts.values() if count > 1
        )
        duplicate_rows = self.duplicate_rows()

        self.metric_pages.value.setText(str(len(active)))
        self.metric_found.value.setText(str(len(serials)))
        self.metric_missing.value.setText(
            str(len(active) - len(serials))
        )
        self.metric_duplicates.value.setText(
            str(max(0, repeated_extra_entries))
        )

        missing = self.missing_count()
        self.review_missing_button.setEnabled(missing > 0)
        self.review_missing_button.setText(
            f"Examinar siguiente sin identificador ({missing})"
            if missing
            else "Examinar siguiente sin identificador"
        )

        self.review_duplicates_button.setEnabled(bool(duplicate_rows))
        self.review_duplicates_button.setText(
            f"Examinar entradas repetidas ({len(duplicate_rows)})"
            if duplicate_rows
            else "Examinar identificadores repetidos"
        )

        self.refresh_duplicate_highlights()

    def open_review(
        self,
        row: int,
        mode: str = "all",
        target_rows: list[int] | None = None,
    ):
        if 0 <= row < len(self.results):
            ReviewDialog(
                self,
                row,
                mode=mode,
                target_rows=target_rows,
            ).exec()

    def review_next_missing(self):
        rows = [
            index
            for index, result in enumerate(self.results)
            if not result.deleted and not result.serial
        ]
        if rows:
            self.open_review(
                rows[0],
                mode="missing",
                target_rows=rows,
            )
            return

        if self.results:
            QMessageBox.information(
                self,
                "Revisión completa",
                "No quedan entradas sin identificador.",
            )

    def review_duplicates(self):
        rows = self.duplicate_rows()
        if rows:
            self.open_review(
                rows[0],
                mode="duplicates",
                target_rows=rows,
            )
            return

        if self.results:
            QMessageBox.information(
                self,
                "Sin entradas repetidas",
                "No hay identificadores repetidos para revisar.",
            )
    def export_zip(self):
        active = [result for result in self.results if not result.deleted]
        if not active:
            return

        if self.document_mode.currentData() == "service":
            duplicate_rows = self.duplicate_rows()
            if duplicate_rows:
                QMessageBox.warning(
                    self,
                    "Folios duplicados en esta sesión",
                    "Corrige los folios repetidos antes de exportar. "
                    "Un mismo folio no puede aparecer dos veces dentro de la sesión actual.",
                )
                self.review_duplicates()
                return

        missing = [result for result in active if not result.serial]
        if missing:
            answer = QMessageBox.question(
                self,
                "Hay páginas sin identificador",
                f"Existen {len(missing)} página(s) sin identificador. "
                "¿Deseas exportarlas con un nombre provisional?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if self.document_mode.currentData() == "service":
            default_name = "Cedulas_por_mes_y_categoria.zip"
        else:
            default_name = (
                f"{Path(self.files[0]).stem}_separado.zip"
                if len(self.files) == 1
                else "PDF_separados_por_identificador.zip"
            )
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar archivo ZIP",
            default_name,
            "Archivo ZIP (*.zip)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not destination:
            return
        if not destination.lower().endswith(".zip"):
            destination += ".zip"

        # Nunca reemplazar un ZIP existente. Si el nombre elegido está ocupado,
        # continuar automáticamente con _2, _3, etc.
        destination = str(next_available_path(destination))

        try:
            with tempfile.TemporaryDirectory(prefix="atlas_pdf_") as temp_dir:
                temp_path = Path(temp_dir)
                used_names: dict[str, int] = {}

                with zipfile.ZipFile(
                    destination,
                    "x",
                    compression=zipfile.ZIP_DEFLATED,
                ) as archive:
                    documents: dict[str, fitz.Document] = {}
                    report_rows: list[list[str | int]] = []
                    try:
                        for index, result in enumerate(active, start=1):
                            document = documents.get(result.source_path)
                            if document is None:
                                document = fitz.open(result.source_path)
                                documents[result.source_path] = document

                            serial = result.serial or (
                                f"SIN_SERIE_{Path(result.source_path).stem}_"
                                f"P{result.page_number:03d}"
                            )
                            base = INVALID_FILENAME.sub("_", serial).strip(" ._")
                            if not base:
                                base = f"SIN_SERIE_{index:03d}"

                            if self.document_mode.currentData() == "service":
                                category = result.category or self.service_fallback_category or "Sin clasificar"
                                safe_category = INVALID_FILENAME.sub("_", category).strip(" ._") or "Sin clasificar"
                                year_name, month_name = date_folder_names(result.report_date)
                                safe_year = INVALID_FILENAME.sub(
                                    "_", year_name
                                ).strip(" ._") or "Año no identificado"
                                safe_month = INVALID_FILENAME.sub(
                                    "_", month_name
                                ).strip(" ._") or "Mes no identificado"
                                archive_folder = f"{safe_year}/{safe_month}/{safe_category}"
                                name_key = f"{archive_folder}/{base}"
                            else:
                                archive_folder = ""
                                name_key = base

                            used_names[name_key] = used_names.get(name_key, 0) + 1
                            occurrence = used_names[name_key]
                            filename = (
                                f"{base}.pdf"
                                if occurrence == 1
                                else f"{base}_{occurrence}.pdf"
                            )

                            output_pdf = fitz.open()
                            output_pdf.insert_pdf(
                                document,
                                from_page=result.page_index,
                                to_page=result.page_index,
                            )
                            page_file = temp_path / filename
                            output_pdf.save(page_file)
                            output_pdf.close()
                            if self.document_mode.currentData() == "service":
                                archive_path = f"{archive_folder}/{filename}"
                            else:
                                archive_path = filename
                            archive.write(page_file, arcname=archive_path)

                            report_rows.append([
                                result.source_name,
                                result.page_number,
                                serial,
                                result.category or "",
                                display_report_date(result.report_date) if result.report_date else "",
                                result.method,
                                result.confidence,
                                archive_path,
                            ])

                        archive.writestr(
                            EXPORT_REPORT_FILENAME,
                            build_export_report_csv(report_rows),
                        )
                    finally:
                        for document in documents.values():
                            document.close()

            history_error = ""
            try:
                service_mode = self.document_mode.currentData() == "service"
                categories = Counter()
                if service_mode:
                    for result in active:
                        category = (
                            result.category
                            or self.service_fallback_category
                            or "Sin clasificar"
                        )
                        categories[category] += 1

                source_files = sorted({
                    str(Path(result.source_path).resolve())
                    for result in active
                })
                append_export_history({
                    "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "document_type": (
                        "Cédulas de servicio" if service_mode else "Equipos"
                    ),
                    "output_zip": str(Path(destination).resolve()),
                    "source_files": source_files,
                    "source_file_count": len(source_files),
                    "page_count": len(active),
                    "identified_count": sum(1 for result in active if result.serial),
                    "provisional_count": sum(1 for result in active if not result.serial),
                    "categories": dict(categories),
                    "report_file": EXPORT_REPORT_FILENAME,
                })
            except OSError as error:
                history_error = str(error)

            unknown_dates = sum(
                1 for result in active
                if self.document_mode.currentData() == "service" and not result.report_date
            )
            detail = (
                f"\n\n{unknown_dates} cédula(s) quedaron en 'Fecha no identificada'."
                if unknown_dates
                else ""
            )
            if history_error:
                detail += (
                    "\n\nEl ZIP se creó correctamente, pero no fue posible guardar "
                    f"el historial local:\n{history_error}"
                )
            else:
                detail += "\n\nLa exportación quedó registrada en el historial local."

            QMessageBox.information(
                self,
                "Exportación terminada",
                f"Se guardaron {len(active)} PDF y el reporte CSV dentro de:\n\n{destination}{detail}",
            )
            self.status_text.setText(
                "ZIP exportado correctamente."
                if history_error
                else "ZIP exportado y registrado en el historial."
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "No se pudo exportar",
                str(error),
            )

    def clear_all(self):
        self.files.clear()
        self.results.clear()
        self.session_duplicate_rejections = 0
        self.rebuild_table()
        self.drop_zone.subtitle.setText("No se ha seleccionado ningún archivo.")
        self.status_text.setText("Esperando uno o varios PDF.")
        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.notice.hide()
        self.results_panel.hide()
        self.update_metrics()
        self.set_controls_state()
