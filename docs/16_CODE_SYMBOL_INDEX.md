# Code Symbol Index

Generated from the actual v1.0.24.23 Python source. This is an implementation inventory, not a conceptual approximation.

## `codecafe_atlas/__init__.py`

- No top-level classes/functions.

## `codecafe_atlas/clean_database.py`

- Function `_table_exists(c, name)`
- Function `_view_exists(c, name)`
- Function `_ensure_clean_sync_records(c)`
- Function `ensure_clean_database(path)`
- Function `_seed(c)`
- Function `_migrate_legacy(source, target)`

## `codecafe_atlas/counter_inserter_engine.py`

- Class `AtlasError`
- Function `normalize_text(value)`
- Function `normalize_serial(value)`
- Function `col_letter(number)`
- Function `is_blank_value(value)`
- Function `parse_number(value)`
- Function `numeric_equal(a, b)`
- Function `display_number(value)`
- Class `TableData`
- Class `FieldMapping`
- Class `MasterLayout`
- Class `MasterRecord`
- Class `FieldDecision`
- Class `MatchDecision`
  - `counter_writable_count(self)`
  - `writable_count(self)`
  - `conflict_count(self)`
- Class `AnalysisResult`
  - `counts(self)`
  - `discrepancy_rows(self)`
  - `updates(self)`
  - `status_updates(self)`
- Class `ODSDocument`
  - `__init__(self, path)`
  - `sheet_names(self)`
  - `sheet_name(sheet)`
  - `find_sheet(self, candidates)`
  - `_row_repeat(row)`
  - `_cell_repeat(cell)`
  - `_set_repeat(element, attr, count)`
  - `get_row(self, sheet, logical_row, split)`
  - `get_cell(self, row, logical_col, split)`
  - `cell_formula(cell)`
  - `cell_value(cell)`
  - `set_numeric_value(cell, value)`
  - `set_text_value(cell, value)`
  - `formula_snapshot(self)`
  - `save(self, output_path)`
- Function `register_namespaces_from_xml(raw)`
- Class `XLSXDocument`
  - `__init__(self, path)`
  - `_load_sheet(self, name, path)`
  - `sheet_names(self)`
  - `sheet_name(self, sheet)`
  - `find_sheet(self, candidates)`
  - `_sheet_data(sheet)`
  - `get_row(self, sheet, logical_row, split)`
  - `_infer_style(self, sheet, row_number, logical_col)`
  - `get_cell(self, row, logical_col, split)`
  - `_cell_xfs(self)`
  - `_style_xf(self, style_id)`
  - `_nearest_existing_zero_style(self, sheet, row_number, logical_col)`
  - `_clone_style_with_numfmt(self, original_style, number_style)`
  - `ensure_zero_visible(self, sheet, row_number, logical_col, cell)`
  - `cell_formula(cell)`
  - `cell_value(self, cell)`
  - `set_numeric_value(cell, value)`
  - `set_text_value(cell, value)`
  - `formula_snapshot(self)`
  - `save(self, output_path)`
- Function `open_master_document(path)`
- Function `iter_ods_rows(table, max_rows, max_cols)`
- Function `read_ods_tables(path)`
- Function `xlsx_col_index(reference)`
- Function `read_xlsx_tables(path)`
- Function `read_csv_tables(path)`
- Function `detect_header_candidates(path, sheet_name, rows)`
- Function `read_report(path)`
- Function `serial_header_score(header)`
- Function `base_field_score(key, header)`
- Function `detect_mapping(headers, allow_partial)`
- Function `locality_header_score(header)`
- Function `_master_header_preview(document, sheet, rows)`
- Function `detect_master_layout(document, sheet)`
- Function `validate_master_layout(document, sheet, expected)`
- Function `load_master_records(document, sheet, layout)`
- Function `_effective_counter_value(item)`
- Function `_operation_status_decision(record, fields)`
- Function `analyze_files(master_path, report_path, overwrite_existing)`
- Function `analyze_multiple_files(master_path, report_paths, overwrite_existing)`
- Function `discrepancy_report_path(output_path)`
- Function `write_discrepancy_report(analysis, output_path)`
- Function `apply_analysis(analysis, output_path)`
- Function `analysis_as_dict(analysis)`
- Function `print_analysis(analysis)`
- Class `AtlasGUI`
  - `__init__(self)`
  - `_build(self)`
  - `select_master(self)`
  - `select_report(self)`
  - `invalidate_analysis(self)`
  - `run_analysis(self)`
  - `populate_preview(self)`
  - `show_details(self, _event)`
  - `set_detail(self, text)`
  - `generate(self)`
  - `run(self)`
- Function `build_arg_parser()`
- Function `main(argv)`

## `codecafe_atlas/counter_inserter_page.py`

- Class `_TaskWorker`
  - `__init__(self, operation)`
  - `run(self)`
- Class `CounterInserterPage`
  - `__init__(self)`
  - `_build_ui(self)`
  - `_select_master(self)`
  - `_select_reports(self)`
  - `_remove_selected_reports(self)`
  - `_clear_reports(self)`
  - `_report_paths(self)`
  - `_invalidate(self)`
  - `_set_busy(self, busy, message)`
  - `_start_task(self, operation, on_success, failure_message)`
  - `_task_failed(self, message, detail)`
  - `_task_finished(self)`
  - `_analyze(self)`
  - `_analysis_completed(self, result)`
  - `_populate(self)`
  - `_show_details(self)`
  - `_generate(self)`
  - `_generation_completed(self, written, equipment, output)`

## `codecafe_atlas/counter_registry_page.py`

- Function `_find_tesseract_executable()`
- Function `_configure_tesseract_environment(executable)`
- Class `CounterDatabaseBridge`
  - `__init__(self, database)`
  - `_response()`
  - `_ocr_capabilities(self)`
  - `ocrCapabilities(self)`
  - `_decode_data_url(data_url)`
  - `_recognize_native(self, data_url, options_payload)`
  - `recognizeImage(self, request_id, data_url, options_payload)`
  - `saveRecords(self, payload)`
  - `listDependencies(self)`
  - `loadRecords(self)`
  - `deleteRecord(self, record_uid)`
  - `clearRecords(self)`
  - `_normalise_export_value(value)`
  - `exportReport(self, payload)`
- Class `CounterRegistryPage`
  - `__init__(self, database)`
  - `load_module(self, force)`
  - `replace_html(self)`
  - `open_folder(self)`

## `codecafe_atlas/data_page.py`

- Class `DataPage`
  - `__init__(self, database, refresh_callback)`
  - `import_database(self)`
  - `export_editable_excel(self)`
  - `reset_database(self)`
  - `create_backup(self)`
  - `show_database_path(self)`

## `codecafe_atlas/database.py`

- Class `Database`
  - `__init__(self, path)`
  - `initialize(self)`
  - `_initialize_application_metadata(self, connection)`
  - `_initialize_service_formats(connection)`
  - `_ensure_column(connection, table, column, declaration)`
  - `_sync_backup_path(self)`
  - `_needs_sync_migration(self, connection)`
  - `_backup_before_sync_migration(self, connection)`
  - `_installation_uuid(self, connection)`
  - `_prepare_sync_identity(self, connection)`
  - `_install_sync_triggers(connection, table, installation_uuid)`
  - `sync_identity_status(self)`
  - `_compose_location_address(row)`
  - `_synchronize_buildings(self, connection)`
  - `list_buildings(self)`
  - `get_building(self, building_id)`
  - `_find_or_create_building(self, connection, name, address)`
  - `_normalize_organizational_name(value)`
  - `_organizational_similarity(cls, left, right)`
  - `similar_buildings(self, name, exclude_id)`
  - `similar_dependencies(self, building_name, name)`
  - `save_building(self, values, building_id)`
  - `directory_equipment(self)`
  - `list_equipment_counter_records(self, equipment_id)`
  - `save_equipment_counter(self, equipment_id, values, record_uid)`
  - `database_health(self)`
  - `connect(self)`
  - `_connect_readonly(path)`
  - `_tables(connection)`
  - `_columns(connection, table)`
  - `_find_table(tables, candidates)`
  - `_pick(row, columns)`
  - `backup(self, backup_dir)`
  - `inspect_database(self, source_path)`
  - `import_existing_database(self, source_path, backup_dir)`
  - `_normalized_serial(value)`
  - `import_preview(self, source_path)`
  - `replace_with_filtered_database(self, source_path, backup_dir)`
  - `reset_to_empty(self, backup_dir)`
  - `_migrate_legacy(self, source_path, backup_path)`
  - `list_dependencies(self, search)`
  - `get_dependency(self, dependency_id)`
  - `save_dependency(self, values, dependency_id)`
  - `update_dependency_city_state(self, dependency_id, city, state)`
  - `delete_dependency(self, dependency_id)`
  - `dependency_choices(self)`
  - `list_equipment(self, search)`
  - `_normalize_equipment_identifier(value)`
  - `find_equipment_duplicate(self, values, exclude_id)`
  - `get_equipment_detailed(self, equipment_id)`
  - `save_equipment(self, values, equipment_id)`
  - `editable_excel_rows(self)`
  - `equipment_duplicate_groups(self)`
  - `merge_duplicate_equipment(self, keep_id, remove_ids)`
  - `dependency_choices_detailed(self)`
  - `equipment_choices_detailed(self)`
  - `list_service_formats(self, search, active_only)`
  - `get_service_format(self, format_id)`
  - `save_service_format(self, values, format_id)`
  - `delete_service_format(self, format_id)`
  - `list_service_orders(self, search)`
  - `save_service_order(self, values, order_id)`
  - `update_service_order_output(self, order_id, output_path)`
  - `delete_service_order(self, order_id)`
  - `_counter_number(value)`
  - `_equipment_id_for_serial(self, connection, serial_number)`
  - `save_counter_records(self, records)`
  - `list_counter_records(self)`
  - `delete_counter_record(self, record_uid)`
  - `clear_counter_records(self)`
  - `counter_record_count(self)`
  - `delete_equipment(self, equipment_id)`

## `codecafe_atlas/directory_page.py`

- Function `_floor_key(value)`
- Function `_address(row)`
- Function `_entry_type(row)`
- Class `DependencyDialog`
  - `__init__(self, database, parent)`
  - `showEvent(self, event)`
  - `_reload_buildings(self, selected_name)`
  - `_sync_inherited_address(self, building_name)`
  - `_confirm_new_building_name(self, name)`
  - `_create_building_inline(self)`
  - `accept(self)`
  - `set_values(self, row)`
  - `values(self)`
- Class `ClickableFrame`
  - `mouseReleaseEvent(self, event)`
- Class `BuildingDialog`
  - `__init__(self, parent)`
  - `set_values(self, row)`
  - `values(self)`
- Class `EquipmentDialog`
  - `__init__(self, database, parent)`
  - `set_values(self, row, dependency_id)`
  - `values(self)`
- Class `CounterDialog`
  - `__init__(self, database, equipment_id, parent)`
  - `_number_text(value)`
  - `_number(value, label, required)`
  - `_update_office(self)`
  - `new_record(self)`
  - `refresh_history(self, select_uid)`
  - `load_selected(self)`
  - `values(self)`
  - `save_record(self)`
  - `delete_record(self)`
- Class `DirectoryPage`
  - `__init__(self, database, on_dependencies_changed)`
  - `clear_form(self)`
  - `refresh(self)`
  - `_refresh_filters(self)`
  - `_row_search_text(self, row)`
  - `_filtered_rows(self)`
  - `_clear_cards(self)`
  - `render(self)`
  - `_building_card(self, building, entries)`
  - `_dependency_block(self, row)`
  - `_equipment_row(self, equipment)`
  - `new_equipment(self, dependency_id)`
  - `edit_equipment(self, equipment_id)`
  - `delete_equipment(self, equipment_id)`
  - `edit_counters(self, equipment_id)`
  - `new_building(self)`
  - `edit_building(self, building_id)`
  - `_confirm_similar_building(self, name, building_id)`
  - `_confirm_similar_dependency(self, values, dependency_id)`
  - `new_entry(self)`
  - `edit_entry(self, dependency_id)`
  - `delete_entry(self, dependency_id)`
  - `print_view(self)`

## `codecafe_atlas/editable_excel_export.py`

- Function `export_editable_excel(path, rows)`

## `codecafe_atlas/export_report.py`

- Function `build_export_report_csv(rows)`

## `codecafe_atlas/formats_page.py`

- Class `FormatsPage`
  - `__init__(self, database)`
  - `_large_notes(placeholder)`
  - `_show_library_placeholder(self)`
  - `_show_editor(self)`
  - `refresh(self)`
  - `selected_id(self)`
  - `load_selected(self)`
  - `values(self)`
  - `save_current(self)`
  - `clear_form(self)`
  - `duplicate_current(self)`
  - `delete_current(self)`
  - `request_current_format(self)`

## `codecafe_atlas/home_page.py`

- Function `_settings_path()`
- Function `load_dashboard_settings()`
- Function `save_dashboard_settings(settings)`
- Class `DashboardCustomizationDialog`
  - `__init__(self, settings, parent)`
  - `_display_path(self)`
  - `choose_image(self)`
  - `restore_default(self)`
  - `result_settings(self)`
- Class `HomePage`
  - `__init__(self)`
  - `_reload_background(self)`
  - `customize_dashboard(self, parent)`
  - `paintEvent(self, event)`

## `codecafe_atlas/identity.py`

- No top-level classes/functions.

## `codecafe_atlas/inventory_page.py`

- Class `InventoryPage`
  - `__init__(self, database, on_equipment_changed)`
  - `refresh_dependencies(self)`
  - `full_refresh(self)`
  - `_natural_text_key(value)`
  - `_ip_key(cls, value)`
  - `_sort_value(self, row, column)`
  - `_sort_key(self, row, column)`
  - `_sorted_rows(self, rows)`
  - `_on_header_clicked(self, column)`
  - `refresh(self)`
  - `load_selected(self)`
  - `clear_form(self)`
  - `values(self)`
  - `save(self)`
  - `select_equipment(self, equipment_id)`
  - `review_duplicates(self)`
  - `delete(self)`

## `codecafe_atlas/main_window.py`

- Class `MainWindow`
  - `__init__(self)`
  - `change_page(self, current, previous)`
  - `apply_service_format(self, format_id)`
  - `open_page(self, key)`
  - `refresh_dependency_consumers(self)`
  - `refresh_all_data(self)`
  - `import_database(self)`
  - `create_backup(self)`
  - `_show_close_notice(self, title, message, icon, timeout_ms)`
  - `closeEvent(self, event)`
  - `show_database_path(self)`
  - `show_update_dialog(self)`
  - `show_about(self)`
  - `show_contact(self)`
- Function `run()`

## `codecafe_atlas/output_filename.py`

- Function `next_available_path(path)`

## `codecafe_atlas/paths.py`

- Function `application_root()`
- Function `bundled_root()`
- Function `asset_path(name)`
- Function `data_dir()`
- Function `_database_counts(path)`
- Function `_database_schema_kind(path)`
- Function `_looks_like_atlas_database(path)`
- Function `_candidate_databases(current)`
- Function `_migrate_previous_database_if_needed(current)`
- Function `database_path()`
- Function `database_migration_message()`
- Function `module_dir(name)`
- Function `dashboard_dir()`
- Function `backups_dir()`

## `codecafe_atlas/pdf_duplicate_tools.py`

- Class `DuplicateScanCancelled`
- Function `path_is_within_root(path, root)`
- Function `sha256_file(path)`
- Function `find_exact_duplicate_groups(paths)`

## `codecafe_atlas/pdf_library_page.py`

- Class `PdfEntry`
  - `display_size(self)`
- Class `PdfLibraryPage`
  - `__init__(self)`
  - `select_folder(self)`
  - `reload_index(self)`
  - `_reload_index(self)`
  - `apply_filter(self)`
  - `open_selected_item(self, current, previous)`
  - `load_document(self, path)`
  - `close_document(self)`
  - `_set_viewer_enabled(self, enabled)`
  - `render_page(self)`
  - `previous_page(self)`
  - `next_page(self)`
  - `rotate(self, degrees)`
  - `change_zoom(self, delta)`
  - `fit_to_width(self)`
  - `eventFilter(self, watched, event)`
  - `_clear_duplicate_state(self)`
  - `toggle_duplicates_only(self, checked)`
  - `detect_duplicates(self)`
  - `_update_duplicate_detail(self, path)`
  - `_clear_current_document(self)`
  - `_path_is_inside_root(self, path)`
  - `delete_selected_pdf(self)`
  - `open_external(self)`
  - `open_containing_folder(self)`
  - `_open_path(path)`
  - `closeEvent(self, event)`

## `codecafe_atlas/pdf_page.py`

- Class `PageResult`
- Function `normalize_serial(value)`
- Function `trim_detected_serial(value)`
- Function `extract_serial(text)`
- Function `extract_service_report(text)`
- Function `format_manual_service_identifier_input(value)`
- Function `normalize_service_identifier(value)`
- Function `find_session_duplicate_identifier(results, identifier)`
- Function `normalize_for_classification(text)`
- Function `classify_service_text(text, rules, fallback)`
- Function `render_service_failure_for_ocr(page)`
- Function `render_service_header_for_ocr(page)`
- Function `render_service_date_for_ocr(page)`
- Function `pixmap_to_png_bytes(pix)`
- Function `page_thumbnail(page, width)`
- Function `render_for_ocr(page)`
- Class `AnalysisWorker`
  - `__init__(self, files, use_ocr, document_mode, category_rules, fallback_category)`
  - `cancel(self)`
  - `run(self)`
- Class `DropZone`
  - `__init__(self)`
  - `mousePressEvent(self, event)`
  - `dragEnterEvent(self, event)`
  - `dragLeaveEvent(self, event)`
  - `dropEvent(self, event)`
- Class `ServiceIdentifierLineEdit`
  - `__init__(self, parent)`
  - `_cursor_after_alphanumeric(value, character_count)`
  - `_apply_identifier_format(self, value)`
- Class `ReportDateLineEdit`
  - `__init__(self, parent)`
  - `_cursor_after_digits(value, digit_count)`
  - `_apply_date_format(self, value)`
- Class `MetricCard`
  - `__init__(self, label)`
- Class `ReviewDialog`
  - `__init__(self, page, row, mode, target_rows)`
  - `current_result(self)`
  - `render_source_page(self)`
  - `load_row(self, row)`
  - `update_navigation_buttons(self)`
  - `display_pixmap(self)`
  - `update_image(self)`
  - `fit_to_width(self)`
  - `rotate_clockwise(self)`
  - `visible_editable_fields(self)`
  - `focus_adjacent_field(self, delta)`
  - `eventFilter(self, watched, event)`
  - `change_zoom(self, delta)`
  - `save_current(self)`
  - `move_position(self, delta)`
  - `save_and_next(self)`
  - `save_and_close(self)`
  - `delete_current(self)`
- Class `ServiceCategoryDialog`
  - `__init__(self, parent)`
  - `load_defaults(self)`
  - `add_rule(self, category, keywords)`
  - `add_empty_row(self)`
  - `remove_selected_row(self)`
  - `values(self)`
- Class `ExportHistoryDialog`
  - `__init__(self, parent)`
  - `_display_timestamp(value)`
  - `_as_int(value, default)`
  - `_category_summary(value)`
  - `reload(self)`
  - `clear_history(self)`
- Class `PdfPage`
  - `__init__(self)`
  - `update_document_mode_labels(self)`
  - `set_controls_state(self, running)`
  - `show_export_history(self)`
  - `choose_files(self)`
  - `choose_folder(self)`
  - `set_files(self, files)`
  - `start_analysis(self)`
  - `cancel_analysis(self)`
  - `on_progress(self, value, text)`
  - `on_page_ready(self, result)`
  - `on_finished(self)`
  - `on_failed(self, message)`
  - `show_notice(self, text, error)`
  - `append_table_row(self, result)`
  - `adjust_table_height(self)`
  - `populate_row(self, row, result)`
  - `refresh_row(self, row)`
  - `rebuild_table(self)`
  - `session_duplicate_row(self, row, serial)`
  - `session_duplicate_message(self, serial, duplicate_row)`
  - `update_serial(self, row, value)`
  - `update_category(self, row, value)`
  - `update_report_date(self, row, value)`
  - `delete_row(self, row)`
  - `missing_count(self)`
  - `serial_counts(self)`
  - `duplicate_serials(self)`
  - `duplicate_rows(self)`
  - `refresh_duplicate_highlights(self)`
  - `update_metrics(self)`
  - `open_review(self, row, mode, target_rows)`
  - `review_next_missing(self)`
  - `review_duplicates(self)`
  - `export_zip(self)`
  - `clear_all(self)`

## `codecafe_atlas/platform_open.py`

- Function `_external_process_environment()`
- Function `_folder_commands(folder)`
- Function `open_directory_native(path)`

## `codecafe_atlas/separator_history.py`

- Function `separator_history_path()`
- Function `_normalized_entry(entry)`
- Function `load_export_history(path)`
- Function `_write_history(records, target)`
- Function `append_export_history(entry, path, limit)`
- Function `clear_export_history(path)`

## `codecafe_atlas/service_document_generator.py`

- Function `safe_filename(value, fallback)`
- Function `full_address(data)`
- Function `city_state(data)`
- Function `write_label_value(ws, cell, label, value)`
- Function `write_value(ws, cell, value)`
- Function `fill_common_header(ws, data, document_type)`
- Function `fill_responsible(ws, data, maintenance)`
- Function `fill_equipment_row(ws, row, data)`
- Function `service_placeholder_values(data)`
- Function `template_placeholders(template_path)`
- Function `validate_service_template(template_path)`
- Function `fill_service_placeholders(ws, data)`
- Function `configure_service_vertical_labels(ws)`
- Function `configure_service_print_layout(ws)`
- Function `fill_service_cell_map(ws, data, cell_map)`
- Function `fill_service_sheet(ws, data, cell_map)`
- Function `fill_maintenance_sheet(ws, data)`
- Function `fill_dictamination_sheet(ws, data)`
- Function `generate_service_document(template_path, output_folder, data)`

## `codecafe_atlas/service_order_page.py`

- Function `read_only_line(placeholder)`
- Function `address_text(row)`
- Function `city_state_text(row)`
- Class `ServiceOrderPage`
  - `__init__(self, database)`
  - `refresh_saved_formats(self, preserve_id)`
  - `apply_selected_saved_format(self)`
  - `apply_saved_format(self, format_id, notify)`
  - `apply_reported_issue_template(self, template_name)`
  - `detect_reported_issue_template(value)`
  - `set_reported_issue_value(self, value)`
  - `_equipment_detail_widgets(self)`
  - `equipment_mode_changed(self, manual)`
  - `_dependency_search_text(row)`
  - `_equipment_search_text(row)`
  - `full_refresh(self)`
  - `refresh_dependencies(self)`
  - `dependency_changed(self)`
  - `fill_dependency_details(self, apply_defaults)`
  - `refresh_equipment(self)`
  - `fill_equipment_details(self)`
  - `update_document_fields(self)`
  - `_load_last_output_folder(self)`
  - `_save_last_output_folder(self, folder)`
  - `_default_output_folder(self)`
  - `choose_output_folder(self)`
  - `_template_validation_message(self, path)`
  - `template_configuration(self)`
  - `active_service_template_path(self)`
  - `active_service_cell_map(self)`
  - `active_service_sheet_name(self)`
  - `ensure_initial_template_configuration(self)`
  - `configure_template(self)`
  - `validate_template(self)`
  - `replace_template(self)`
  - `restore_default_template(self)`
  - `open_module_folder(self)`
  - `field_values(self)`
  - `validate(self, values, require_output)`
  - `resolve_equipment(self, values)`
  - `sync_dependency_city_state(self, values)`
  - `save_record(self)`
  - `show_document_preview(self)`
  - `generate_document(self)`
  - `refresh_history(self)`
  - `_set_date(widget, value)`
  - `_set_time(widget, value)`
  - `load_selected_order(self)`
  - `clear_form(self)`
  - `delete_record(self)`
  - `open_selected_file(self)`

## `codecafe_atlas/service_report_date.py`

- Function `_ascii_text(value)`
- Function `_token_to_int(token)`
- Function `_validated_iso(day_token, month_token, year_token)`
- Function `_extract_first_date(value, allow_space_separators)`
- Function `extract_provider_report_date(text)`
- Function `format_manual_report_date_input(value)`
- Function `parse_manual_report_date(value)`
- Function `display_report_date(iso_date)`
- Function `date_folder_names(iso_date)`
- Function `year_folder_name(iso_date)`
- Function `month_folder_name(iso_date)`

## `codecafe_atlas/service_template_config.py`

- Function `load_template_settings(path)`
- Function `save_template_settings(path, payload)`
- Function `normalize_cell_list(value)`
- Function `workbook_sheet_names(path)`
- Class `ServiceTemplateConfigDialog`
  - `__init__(self, parent)`
  - `select_included(self)`
  - `select_custom(self)`
  - `inspect_selected_template(self)`
  - `_cell_map(self)`
  - `accept_configuration(self)`

## `codecafe_atlas/sync_compare_page.py`

- Class `SyncComparePage`
  - `__init__(self, database)`
  - `_build_ui(self)`
  - `_browse(self)`
  - `_compare(self)`
  - `_populate(self)`
  - `_homologate(self)`
  - `_export(self)`

## `codecafe_atlas/sync_engine.py`

- Class `SyncItem`
- Class `SyncPlan`
  - `close(self)`
- Class `SyncEngine`
  - `__init__(self, local_path, external_path)`
  - `connect(path, ro)`
  - `tables(connection)`
  - `cols(connection, table)`
  - `norm(value)`
  - `_is_clean(connection)`
  - `validate_clean(self, path, label)`
  - `prepare(self)`
  - `payload(row, columns)`
  - `_sync_uuid(connection, table, entity_id)`
  - `_building_name(connection, building_id)`
  - `_dependency_name(connection, dependency_id)`
  - `_person_name(connection, person_id)`
  - `natural_key(self, connection, table, row)`
  - `identifier(self, connection, table, row)`
  - `_dependency_token(self, connection, dependency_id)`
  - `_equipment_token(self, connection, equipment_id)`
  - `comparison_payload(self, connection, table, row, columns)`
  - `_normalized_payload(payload)`
  - `_difference(local_payload, external_payload)`
  - `analyze(self)`
  - `_backup(self)`
  - `_upsert_sync_identity(connection, table, entity_id, record_uuid, external_connection, external_id)`
  - `apply(self, plan, report_dir)`

## `codecafe_atlas/ui_helpers.py`

- Function `page_header(title, subtitle)`
- Function `line_edit(placeholder)`
- Function `notes_edit(placeholder)`
- Function `standard_actions()`

## `codecafe_atlas/update_dialog.py`

- Class `UpdateDialog`
  - `__init__(self, current_version, parent)`
  - `choose_package(self)`
  - `validate_package(self, selected)`
  - `install_update(self)`

## `codecafe_atlas/updater.py`

- Class `UpdatePackageError`
- Class `UpdatePackageInfo`
- Function `version_tuple(version)`
- Function `current_platform_name()`
- Function `current_architecture()`
- Function `_safe_member_path(name)`
- Function `read_update_manifest(package_path)`
- Function `inspect_update_package(package_path, current_version, require_newer)`
- Function `updater_program_path()`
- Function `launch_external_updater(package_path, current_version)`

## `codecafe_atlas_updater.py`

- Function `bundled_root()`
- Function `asset_path(name)`
- Function `wait_for_process(pid, timeout)`
- Function `safe_extract(archive, destination)`
- Function `merge_directory(source, destination)`
- Function `apply_manifest_modes(root, manifest)`
- Function `_main_name()`
- Function `validate_payload_root(payload)`
- Function `restart_application(target)`
- Function `perform_update(package, target, pid, progress, restart)`
- Class `UpdateThread`
  - `__init__(self, package, target, pid)`
  - `run(self)`
- Class `UpdaterWindow`
  - `__init__(self, args)`
  - `closeEvent(self, event)`
  - `on_progress(self, value, text)`
  - `on_success(self, backup_path)`
  - `on_failure(self, details)`
- Function `parse_arguments()`
- Function `main()`

## `main.py`

- No top-level classes/functions.

## `make_update_package.py`

- Function `sha256_file(path)`
- Function `default_platform()`
- Function `default_architecture()`
- Function `validate_distribution(dist, platform_name)`
- Function `main()`

## `validate_before_build.py`

- No top-level classes/functions.

## `validate_full_functionality.py`

- Function `require(path)`
- Function `require_methods(path, class_name, methods)`

## `validate_public_identity.py`

- No top-level classes/functions.
