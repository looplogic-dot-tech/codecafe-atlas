# CodeCafe Atlas v1.0.24.23 — Technical Documentation Index

This documentation is derived from the actual v1.0.24.23 source archive, not reconstructed from memory.

**Reference source SHA-256:** `3bf57b88cd0cd417116ba30291a3ceda9978d5cf6905e13c2c3668bd2bff36de`

## Purpose

The goal is reproducibility: a future maintainer should be able to understand what Atlas does, how it is implemented, where state lives, how its SQLite compatibility layer works, how to build it, how to validate it, how to recover it, and which architectural rules must not be broken.

## Reading order

1. `01_SYSTEM_OVERVIEW.md`
2. `02_SOURCE_TREE_AND_COMPONENT_MAP.md`
3. `03_RUNTIME_BOOT_SEQUENCE.md`
4. `04_DATABASE_SCHEMA_AND_COMPATIBILITY.md`
5. `05_DATABASE_API_REFERENCE.md`
6. `06_UI_MODULE_INTERNALS.md`
7. `07_DOCUMENT_WORKFLOWS_INTERNALS.md`
8. `08_PDF_AND_COUNTER_INTERNALS.md`
9. `09_HOMOLOGATION_AND_SYNC_INTERNALS.md`
10. `10_CONFIGURATION_AND_STATE_FILES.md`
11. `11_BUILD_PACKAGING_AND_UPDATER.md`
12. `12_VALIDATION_AND_TESTING.md`
13. `13_REPRODUCIBILITY_RUNBOOK.md`
14. `14_PLUGIN_ARCHITECTURE_ROADMAP.md`
15. `15_BASELINE_AND_CHANGE_CONTROL.md`
16. `16_CODE_SYMBOL_INDEX.md`
17. `17_SCHEMA_DDL_REFERENCE.md`
18. `18_DEPENDENCIES_AND_EXTERNAL_REQUIREMENTS.md`
19. `19_FAILURE_RECOVERY_AND_TROUBLESHOOTING.md`
20. `20_SECURITY_PRIVACY_AND_PUBLIC_SOURCE.md`

## Authority order

When documents conflict, use this order:

1. actual v1.0.24.23 source code;
2. `CODECAFE_ATLAS_IDENTITY.json`;
3. SQLite schema in `codecafe_atlas/clean_database.py`;
4. validation scripts;
5. this documentation;
6. historical change notes.

Historical notes describe earlier states and must not override current source.
