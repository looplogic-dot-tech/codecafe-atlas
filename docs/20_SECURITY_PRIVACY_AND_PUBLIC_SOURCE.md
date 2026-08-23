# Security, Privacy and Public Source

## Public repository boundary

Do not publish:
- operational SQLite DBs;
- DB backups;
- real workplace Excel/CSV exports;
- real processed PDFs;
- credentials/tokens;
- private infrastructure details;
- personal contact datasets.

## Included public source state

A public source distribution should contain empty writable `data/` and `backups/` directories, not an operational DB.

## Update security

Updater extraction validates archive paths to prevent traversal outside the temporary extraction root.

Update packages use SHA-256 metadata/manifests for file validation.

## External OCR/privacy

Native Tesseract is local. Any future external OCR fallback must clearly disclose when document/image data leaves the machine.

## Authentication

Desktop v1.0.24.23 is not the future web authorization model. Atlas Web must add server-side authentication, authorization and audit controls before exposing production write operations.
