# CodeCafe Atlas v1.0.24.15

**CodeCafe Atlas** is a cross-platform desktop application designed to organize equipment, locations, operational records, document-processing workflows, and related technical information through a unified graphical interface.

The project is written primarily in Python and uses PySide6 for its desktop interface. It is designed to run on Linux and Windows and can be packaged as a standalone desktop application.

## Current Version

**v1.0.24.15**

This repository contains the clean public source corresponding to the current v1.0.24.15 milestone.

## Main Features

### Directory

Hierarchical organization of operational locations and dependencies, including:

- Buildings
- Floors and locations
- Dependencies
- Contact and administrative information
- Equipment associated with each dependency
- Search and filtering
- Editable records

### Equipment Inventory

Centralized equipment inventory with information such as:

- Serial number
- Manufacturer and model
- Assigned location
- Dependency
- User or workgroup assignment
- Equipment status
- Installation information
- Notes and related operational data

Serial numbers are treated as unique equipment identifiers to help prevent duplicate inventory records.

### Counter Registry

Tools for processing and recording printer counter information.

Atlas can maintain historical counter records associated with equipment while preserving the relationship between the counter reading and the corresponding device.

### Intelligent PDF Processing

Includes utilities for document-processing workflows such as:

- PDF separation
- Classification workflows
- Processing of supported document formats
- Tracking processed documents without requiring the original documents to be permanently stored in the application database

### Service Document Generation

Atlas includes tools for generating service documentation from configurable templates and structured data.

### Data Administration

Database-management tools allow Atlas data to be inspected, exported and managed through the application.

The application uses SQLite for local structured data storage.

Operational databases and organization-specific production data are **not included in this public repository**.

## Database Architecture

Atlas organizes operational information around a hierarchical model:

**Building → Dependency → Equipment**

Equipment records can also maintain associated operational information such as location, assignment and counter history.

The database is intentionally separated from the public source distribution so that the application source can be published without exposing operational or organization-specific information.

## Duplicate Protection

Atlas includes safeguards intended to maintain database integrity.

Equipment serial numbers are unique identifiers, and duplicate equipment records should not be created when the same serial number already exists.

Dependencies are also protected against accidental duplication. Similar dependency names can require review rather than being silently merged.

## Technology

The project uses technologies including:

- Python 3
- PySide6 / Qt
- SQLite
- openpyxl
- PyMuPDF
- Pillow
- pytesseract
- PyInstaller

Some document-processing functions may require external OCR components such as Tesseract.

## Supported Platforms

CodeCafe Atlas is designed for:

- Linux
- Windows

Platform-specific build scripts are included in the repository.

## Building

Install the required Python dependencies:

```bash
python3 -m pip install -r requirements.txt
