# Database API Reference

`codecafe_atlas.database.Database` is the primary data service used by UI modules.

## Initialization/health
- `initialize()`
- `database_health()`
- `sync_identity_status()`
- `connect()`

## Buildings / organizational duplicate protection
- `list_buildings()`
- `get_building()`
- `save_building()`
- `similar_buildings()`
- `_normalize_organizational_name()`
- `_organizational_similarity()`

## Dependencies
- `list_dependencies()`
- `get_dependency()`
- `save_dependency()`
- `delete_dependency()`
- `dependency_choices()`
- `dependency_choices_detailed()`
- `similar_dependencies()`
- `update_dependency_city_state()`

## Equipment
- `list_equipment()`
- `directory_equipment()`
- `get_equipment_detailed()`
- `save_equipment()`
- `delete_equipment()`
- `find_equipment_duplicate()`
- `equipment_duplicate_groups()`
- `merge_duplicate_equipment()`
- `equipment_choices_detailed()`

## Counter history
- `save_counter_records()`
- `list_counter_records()`
- `delete_counter_record()`
- `clear_counter_records()`
- `counter_record_count()`
- `list_equipment_counter_records()`
- `save_equipment_counter()`

## Service formats/orders
- `list_service_formats()`
- `get_service_format()`
- `save_service_format()`
- `delete_service_format()`
- `list_service_orders()`
- `save_service_order()`
- `update_service_order_output()`
- `delete_service_order()`

## Administration
- `backup()`
- `inspect_database()`
- `import_existing_database()`
- `import_preview()`
- `replace_with_filtered_database()`
- `reset_to_empty()`
- `editable_excel_rows()`

## Important rule

UI code should prefer this API instead of embedding new direct SQL. Direct canonical SQL exists in some specialized/recovery paths, but expanding that pattern increases coupling and makes future web/plugin migration harder.
