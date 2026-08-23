# Reproducibility Corrections Applied to the Documented Copy

The reference v1.0.24.23 ZIP is preserved as the behavioral baseline. During a clean extraction audit, three XLSX member names were found stored with mojibake (`C├⌐dula`) even though the source code and validator expect `Cédula`.

For the **fully documented reproducible source copy only**, the following filenames were normalized without changing workbook bytes or application logic:

- `Formato de referencia - Cédula de Servicio.xlsx`
- `Plantilla predeterminada - Cédula de Servicio.xlsx`
- `Formato de referencia - Cédulas.xlsx`

Reason: a clean extraction of the reference ZIP otherwise causes `validate_before_build.py` to report that the required service template is missing.

After normalization, the actual project validators were executed successfully:

- `validate_public_identity.py` — PASS / zero forbidden-name occurrences
- `validate_full_functionality.py` — PASS
- `validate_before_build.py` — PASS

No database schema, Python logic, workbook content or runtime behavior was changed by this correction.

A separate cosmetic inconsistency remains in `build_windows.bat`: one completion message still says `v1.0.24.16`; the package-generation command correctly uses `1.0.24.23`. This is documented rather than silently changing the behavioral baseline.
