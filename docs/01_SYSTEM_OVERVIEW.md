# System Overview

## Product identity

CodeCafe Atlas is a local-first operational desktop suite written in Python and PySide6. Version 1.0.24.23 identifies itself as:

- product: CodeCafe Atlas
- application ID: `io.codecafe.atlas`
- origin ID: `CCA-JSS-2026`
- brand: CodeCafe.io
- database compatibility flag: enabled

## Architectural shape

Atlas is a monolithic desktop application with modular pages sharing one `Database` service.

```text
main.py
  -> codecafe_atlas.main_window.run()
      -> QApplication
      -> MainWindow
          -> Database(data/atlas.db)
          -> page modules
          -> backup/update integration
```

The UI modules do not each own separate production databases. The authoritative operational database is `data/atlas.db`.

## Major functional areas

- Dashboard
- Directory
- Inventory
- Counter Registry
- Counter Inserter
- PDF Separator
- PDF Viewer
- Service Orders / document generation
- Format/template administration
- Data administration/import/reset/backups
- Database homologation/synchronization
- Integrated updater

## Core data philosophy

The current canonical organizational model is:

```text
Building
  -> Dependency
      -> optional Office
      -> Equipment
          -> historical Counter Readings
```

People are separate entities and are linked to dependencies/equipment.

Directory and Inventory are different views of the same canonical equipment records.

## Specialized modules

The current Service Order generator, PDF Separator and Counter Registry are optimized for an existing operational workflow. They are part of v1.0.24.23, but the future architecture should allow these specialized workflows to be replaceable plugins instead of forcing every deployment to use them.
