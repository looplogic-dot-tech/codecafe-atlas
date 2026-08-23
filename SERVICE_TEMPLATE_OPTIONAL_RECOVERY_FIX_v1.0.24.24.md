# Service template optional recovery fix — v1.0.24.24

Production build validation no longer requires the bundled recovery workbook to exist under an exact historical filename.

- A user-supplied Excel template can be the sole active service-certificate template.
- If the bundled recovery workbook is present, it is still validated and the Restore button remains available.
- If it is absent, the Restore button is disabled and the template configurator continues to support loading a custom workbook.
- This removes a build-time dependency on historical service-template files without changing the database schema or other Atlas modules.
