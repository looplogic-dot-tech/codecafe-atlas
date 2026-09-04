# Dependencies and External Requirements

## Python packages

From `requirements.txt`:
- PySide6 >= 6.7, < 7
- PyInstaller >= 6.0, < 7
- openpyxl >= 3.1, < 4
- PyMuPDF >= 1.24, < 2
- Pillow >= 10, < 13
- pytesseract >= 0.3.13, < 1

## System OCR

Native OCR requires the Tesseract executable. Language availability determines OCR capabilities.

Typical Debian/Ubuntu/Kubuntu installation:

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa
```

## Desktop integration

Folder/file opening depends on platform tools:
- Linux/KDE: Dolphin and fallbacks such as `kioclient`, `gio`, `xdg-open`
- Windows: Explorer/shell integration
- macOS: `open`

`platform_open.py` sanitizes the PyInstaller process environment before spawning system desktop tools.

## Spreadsheet formats

Counter Inserter contains dedicated document abstractions for XLSX and ODS, plus report readers for CSV/XLSX/ODS.

## PDF

PyMuPDF is the native PDF processing/rendering dependency.
