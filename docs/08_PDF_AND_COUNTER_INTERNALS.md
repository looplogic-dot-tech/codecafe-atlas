# PDF and Counter Internals

## PDF Separator
`pdf_page.py`

This is a native PySide6/PyMuPDF workflow.

Core internals include:
- file/folder input;
- text extraction;
- local OCR fallback;
- serial/service identifier detection;
- service report date extraction;
- category classification;
- thumbnail/review rendering;
- manual correction;
- duplicate-session identifier checks;
- delete-and-continue review behavior;
- ZIP export;
- CSV export report;
- persistent export-history metadata.

Review is handled by `ReviewDialog`; background processing by `AnalysisWorker`.

## Separator history
`separator_history.py`

Stores normalized export metadata in local state. It does not duplicate the original PDFs.

## PDF Viewer
`pdf_library_page.py` plus `pdf_duplicate_tools.py`

Provides local indexing/viewing and exact duplicate detection based on content/hash behavior.

## Counter Registry
`counter_registry_page.py`

`CounterDatabaseBridge` is a bridge between the counter UI and Python services:
- native Tesseract capability detection;
- OCR requests;
- dependency listing;
- save/load/delete history;
- report export.

`CounterRegistryPage` owns module loading and folder operations.

## Counter Inserter
`counter_inserter_engine.py`

This is a substantial spreadsheet engine independent of the Qt page.

It supports XLSX and ODS master documents, parses multiple report sources, detects layout/header mappings, matches by normalized serial, protects formulas/authorized ranges, generates discrepancies and writes a verified copy.

The Qt wrapper is `counter_inserter_page.py`.

The engine and page should be treated separately when debugging: UI problems do not necessarily imply spreadsheet-engine problems.
