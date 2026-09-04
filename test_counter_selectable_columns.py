from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from codecafe_atlas import counter_inserter_engine as engine


def main() -> None:
    assert engine.configure_target_columns("R,S,V,W") == "R,S,V,W"
    assert [item[0] for item in engine.TARGETS] == ["R", "S", "V", "W"]
    assert list(engine.TARGET_BY_KEY) == [
        "principal", "equivalente", "duplex", "atascos"
    ]
    assert engine.configure_targets_without_reserved_location(
        "P,R,S,V,W", engine.column_number("P")
    ) == "R,S,V,W"
    assert [item[0] for item in engine.TARGETS] == ["R", "S", "V", "W"]

    headers = [
        "Zona", "Auxiliar", "Modelo", "Dependencia", "Número de serie",
        "Fecha", "Total de impresiones", "Carta", "Hojas ambas caras",
        "Eventos de atasco",
    ]
    source = engine.configure_source_mapping(headers, "E")
    assert source.serial_col == 4
    assert set(source.fields) == {"principal", "equivalente", "duplex", "atascos"}

    correction_report = engine.TableData(
        source_path=Path("atlas.db"),
        sheet_name="Base de datos de Atlas",
        header_row=1,
        headers=["Número de serie", "Total de impresiones"],
        rows=[["3356P51635", 1234], ["VNB0B01985", 5678]],
        source_record_count=2,
        source_unique_count=2,
    )
    correction_mapping = engine.configure_source_mapping(correction_report.headers, "AUTO")
    corrected_report = engine.apply_serial_overrides(
        correction_report,
        correction_mapping,
        {"3356P51635": "3356P351635"},
    )
    assert corrected_report.rows[0][0] == "3356P351635"
    assert corrected_report.rows[0][1] == 1234
    assert corrected_report.rows[1] == correction_report.rows[1]
    assert correction_report.rows[0][0] == "3356P51635"

    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "atlas.db"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE atlas_dependencies (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.execute(
            """CREATE TABLE atlas_equipment (
                id INTEGER PRIMARY KEY, dependency_id INTEGER, serial_number TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE atlas_counter_readings (
                id INTEGER PRIMARY KEY, equipment_id INTEGER, reading_date TEXT, serial_snapshot TEXT,
                total_prints REAL, letter_prints REAL, duplex_sheets REAL,
                jam_events REAL
            )"""
        )
        connection.execute("INSERT INTO atlas_dependencies VALUES (1, 'Juzgado Primero')")
        connection.executemany(
            "INSERT INTO atlas_equipment VALUES (?,?,?)",
            [(10, 1, "SERIE-1"), (11, 1, "SERIE-2"), (12, 1, "SERIE-3")],
        )
        connection.executemany(
            "INSERT INTO atlas_counter_readings VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, 10, "2026-08-01", "SERIE-1", 100, 90, 20, 1),
                (2, 10, "2026-09-01", "SERIE-1", 150, 130, 30, 2),
                (3, 11, "2026-08-15", "SERIE-2", 75, 70, 10, 0),
            ],
        )
        connection.commit()
        connection.close()
        db_report = engine.read_atlas_counter_database(database)
        assert len(db_report.rows) == 3
        assert db_report.rows[0] == ["SERIE-1", 150.0, 130.0, 30.0, 2.0, "Juzgado Primero"]
        assert db_report.rows[2] == ["SERIE-3", None, None, None, None, "Juzgado Primero"]
        assert engine.source_dependency_column(db_report.headers) == 5
        db_mapping = engine.configure_source_mapping(db_report.headers, "AUTO")
        assert set(db_mapping.fields) == {"principal", "equivalente", "duplex", "atascos"}
        assert db_report.source_record_count == 3
        assert db_report.source_unique_count == 3

    location_record = engine.MasterRecord(
        20, "SERIE-1", "SERIE1", "Torreón", {}, current_location=""
    )
    assert engine._equipment_location_decision(
        location_record, "Juzgado Primero", 16, "fill"
    ) == ("escribir", "Juzgado Primero")
    location_record.current_location = "Ubicación anterior"
    assert engine._equipment_location_decision(
        location_record, "Juzgado Primero", 16, "fill"
    )[0] == "conservar"
    assert engine._equipment_location_decision(
        location_record, "Juzgado Primero", 16, "replace"
    )[0] == "sobrescribir"
    location_record.current_location = "Juzgado primero"
    assert engine._equipment_location_decision(
        location_record, "Juzgado Primero", 16, "replace"
    )[0] == "sobrescribir"
    assert engine.equipment_location_header_score("Ubicación de Equipo") >= 120

    assert engine.serial_edit_distance("VNB0B02006", "VNB0B020O6") == 1
    assert engine.serial_edit_distance("VNB0B02006", "VNB0B02060") == 1

    assert engine.configure_target_range("AS") == "AS:AZ"
    assert [item[0] for item in engine.TARGETS] == [
        "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ"
    ]
    assert engine.TARGET_BY_KEY["principal"][0] == "AS"
    assert engine.TARGET_BY_KEY["digitalizaciones"][0] == "AZ"
    assert engine.TARGET_COLS == set(range(45, 53))

    for invalid in ("", "AS:AY", "AS:BA", "AZ:AS", "1:8", "XFA"):
        try:
            engine.configure_target_range(invalid)
        except engine.AtlasError:
            pass
        else:
            raise AssertionError(f"Se aceptó el rango inválido {invalid!r}")

    assert engine.configure_target_range("ak:ar") == "AK:AR"
    print("SELECTABLE MONTHLY COUNTER COLUMNS: PASS")


if __name__ == "__main__":
    main()
