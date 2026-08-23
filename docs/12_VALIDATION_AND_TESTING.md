# Validation and Testing

## `validate_before_build.py`

This is a pre-build regression gate, not merely a syntax check.

It performs:
- compile check of Python modules;
- method-presence checks for approved Service Order workflow;
- template placeholder validation;
- Directory feature guards;
- empty-DB initialization test;
- SQLite integrity/FK checks;
- canonical table checks;
- sync identity check;
- build-script public-data protections;
- additional feature guards accumulated by the project.

## `validate_full_functionality.py`

Accumulated feature-presence guard intended to catch silent regressions in modules that were previously approved.

## `validate_public_identity.py`

Public-source identity scanner. It is intended to reject forbidden legacy naming in paths/content and protect the clean public source boundary.

## Build smoke test

Linux build starts the frozen app under:

`QT_QPA_PLATFORM=offscreen`

with a timeout. It scans log output for fatal startup patterns.

## What automated validation cannot prove

Static/automated guards cannot fully prove:
- real desktop file-manager integration;
- OCR quality on production documents;
- production spreadsheet variations;
- visual scaling on every Windows/Linux display;
- every real database edge case;
- operator workflow correctness.

Production acceptance still matters.
