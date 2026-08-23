# Document Workflows Internals

## Operational UI
`service_order_page.py`

The page:
- refreshes dependencies/equipment from canonical data;
- can select existing equipment or capture new equipment;
- fills dependency/equipment details;
- persists output-folder preference;
- validates operational fields;
- saves service-order records;
- previews and generates documents;
- manages generated-file opening;
- integrates reusable saved formats.

## Generator
`service_document_generator.py`

The generator uses `openpyxl` and supports:
- placeholder extraction/validation;
- placeholder replacement;
- direct field-to-cell mapping;
- worksheet selection;
- print-layout configuration;
- template-specific generation logic.

## Template configuration
`service_template_config.py`

First-use/customization layer:
- choose included template or custom workbook;
- inspect workbook sheets;
- configure target worksheet;
- map Atlas fields to cells;
- save the mapping to local configuration.

The normal runtime should not require a user to edit Python to change where fields land in the spreadsheet.

## Separation of responsibilities

- Service Order page = operational data entry/execution.
- Format library = reusable template/format catalog and configuration.
- Generator = workbook rendering engine.
- Template configuration = binding between Atlas business fields and workbook cells.

## Future custom modules

The current generator should eventually be one replaceable implementation. A custom deployment may need invoices, contracts, different work orders or another document engine.
