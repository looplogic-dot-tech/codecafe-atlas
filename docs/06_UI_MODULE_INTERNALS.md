# UI Module Internals

## Main window
The main window owns navigation and page lifetime. Page state is intended to persist while switching modules unless a module explicitly refreshes.

## Directory
`directory_page.py`

Key components:
- `DependencyDialog`
- `ClickableFrame`
- building/dependency display widgets
- inline building creation
- inherited address synchronization
- duplicate/similarity confirmation

The building field is an editable selector: existing buildings can be selected, while a new building can be added.

Directory must count equipment from the same canonical equipment set used by Inventory.

## Inventory
`inventory_page.py`

Responsibilities include:
- canonical equipment listing
- edit/persist
- row numbering and total
- filtering
- sortable columns
- duplicate group review
- duplicate merge workflow
- editable Excel export integration

## Data Administration
`data_page.py`

Exposes:
- DB import/preview
- editable Excel export
- reset to empty
- manual backup
- active DB location

## Format library
`formats_page.py`

Current intent is library/configuration behavior. A specialized document form should not permanently occupy the detail panel when no format is selected.

## Shared platform folder opening
`platform_open.py` centralizes opening folders/files externally. It sanitizes the environment inherited from PyInstaller before launching desktop file managers.
