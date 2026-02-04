"""
DEPRECATED: app.utility package has been consolidated into app.shared.toolkit.

All modules have been migrated. Use the canonical imports:
- app.shared.toolkit.logging  (logger, get_request_id, set_request_id)
- app.shared.toolkit.auth     (require_admin, get_current_role, Role)
- app.shared.toolkit.helpers   (get_client_ip, clean_xml_dict, safe_dict_get)
- app.shared.toolkit.circuit_breaker (AppCircuitBreaker, ...)
- app.shared.toolkit.export    (report_to_json, report_to_csv, ...)
- app.shared.toolkit.pdf       (save_pdf_report, generate_analysis_pdf, ...)
- app.shared.toolkit.telemetry (init_telemetry, get_span_exporter, ...)
- app.shared.toolkit.metrics   (app_metrics)
- app.shared.decorators        (retry, cache_with_tarantool, ...)
"""
