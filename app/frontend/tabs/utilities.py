from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.api_client import ApiClient


def _bool_param(val: bool) -> str:
    return "true" if val else "false"


def render(api: ApiClient, *, admin_token: str) -> None:
    st.header("Утилиты (admin)")

    st.info("Эта вкладка доступна только в админ-режиме. Destructive операции требуют подтверждения.")

    st.subheader("Health")
    deep = st.checkbox("deep=true", value=False)
    if st.button("Проверить /utility/health", type="primary"):
        payload = api.get("/utility/health", params={"deep": _bool_param(deep)}, admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    st.divider()

    st.subheader("Config")
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Снимок /utility/config"):
            cfg = api.get("/utility/config", admin_token=admin_token)
            if cfg is not None:
                st.session_state["utility_config_snapshot"] = cfg
    with col2:
        confirm_reload = st.checkbox("confirm reload", value=False)
        if st.button("Перезагрузить конфиг /utility/config/reload", disabled=not confirm_reload):
            resp = api.post("/utility/config/reload", admin_token=admin_token)
            if resp is not None:
                st.json(resp)
    cfg_snapshot = st.session_state.get("utility_config_snapshot")
    if cfg_snapshot:
        with st.expander("config snapshot", expanded=False):
            st.json(cfg_snapshot)

    st.divider()

    st.subheader("Circuit breakers")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("App CB status"):
            payload = api.get("/utility/app-circuit-breaker", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with c2:
        confirm_reset_app = st.checkbox("confirm app-cb reset", value=False)
        if st.button("App CB reset", disabled=not confirm_reset_app):
            payload = api.post("/utility/app-circuit-breaker/reset", admin_token=admin_token)
            if payload is not None:
                st.json(payload)

    st.markdown("**Сервисные circuit breakers**")
    cb = api.get("/utility/circuit-breakers", admin_token=admin_token)
    if cb is not None:
        with st.expander("circuit breakers status", expanded=False):
            st.json(cb)
        services = []
        if isinstance(cb, dict):
            services = sorted(list((cb.get("breakers") or {}).keys()))
        service = st.selectbox("service", options=services or ["perplexity", "tavily", "openrouter"], index=0)
        confirm_reset = st.checkbox("confirm service reset", value=False, key="cb_confirm_service_reset")
        if st.button("Reset service breaker", disabled=not confirm_reset):
            payload = api.post(f"/utility/circuit-breakers/{service}/reset", admin_token=admin_token)
            if payload is not None:
                st.json(payload)

    st.divider()

    st.subheader("Metrics")
    colm1, colm2, colm3 = st.columns(3)
    with colm1:
        if st.button("GET /utility/metrics"):
            payload = api.get("/utility/metrics", admin_token=admin_token)
            if payload is not None:
                st.session_state["utility_metrics"] = payload
    with colm2:
        confirm_reset_metrics = st.checkbox("confirm metrics reset", value=False)
        if st.button("POST /utility/metrics/reset", disabled=not confirm_reset_metrics):
            payload = api.post("/utility/metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with colm3:
        confirm_reset_app_metrics = st.checkbox("confirm app-metrics reset", value=False)
        if st.button("POST /utility/app-metrics/reset", disabled=not confirm_reset_app_metrics):
            payload = api.post("/utility/app-metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    if st.session_state.get("utility_metrics"):
        with st.expander("metrics", expanded=False):
            st.json(st.session_state["utility_metrics"])

    st.divider()

    st.subheader("Cache / Tarantool")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Tarantool status"):
            payload = api.get("/utility/tarantool/status", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with c2:
        if st.button("Cache metrics"):
            payload = api.get("/utility/cache/metrics", admin_token=admin_token)
            if payload is not None:
                st.session_state["utility_cache_metrics"] = payload
    with c3:
        confirm_cache_metrics_reset = st.checkbox("confirm cache metrics reset", value=False)
        if st.button("Reset cache metrics", disabled=not confirm_cache_metrics_reset):
            payload = api.post("/utility/cache/metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    if st.session_state.get("utility_cache_metrics"):
        with st.expander("cache metrics", expanded=False):
            st.json(st.session_state["utility_cache_metrics"])

    st.markdown("**Cache entries / reset by prefix**")
    limit = st.number_input("entries limit", min_value=1, max_value=100, value=10)
    if st.button("Показать /utility/cache/entries"):
        payload = api.get("/utility/cache/entries", params={"limit": int(limit)}, admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    prefix = st.text_input("prefix", value="search:")
    confirm_prefix = st.checkbox("confirm delete prefix", value=False)
    if st.button("DELETE /utility/cache/prefix/{prefix}", disabled=not confirm_prefix):
        payload = api.delete(f"/utility/cache/prefix/{prefix}", admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    st.divider()

    st.subheader("Внешние сервисы")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        if st.button("Perplexity status"):
            payload = api.get("/utility/perplexity/status", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with s2:
        if st.button("Tavily status"):
            payload = api.get("/utility/tavily/status", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with s3:
        if st.button("OpenRouter status"):
            payload = api.get("/utility/openrouter/status", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with s4:
        if st.button("Email status"):
            payload = api.get("/utility/email/status", admin_token=admin_token)
            if payload is not None:
                st.json(payload)

    clear1, clear2 = st.columns(2)
    with clear1:
        confirm_t = st.checkbox("confirm clear tavily cache", value=False)
        if st.button("Clear Tavily cache", disabled=not confirm_t):
            payload = api.post("/utility/tavily/cache/clear", admin_token=admin_token)
            if payload is not None:
                st.json(payload)
    with clear2:
        confirm_p = st.checkbox("confirm clear perplexity cache", value=False)
        if st.button("Clear Perplexity cache", disabled=not confirm_p):
            payload = api.post("/utility/perplexity/cache/clear", admin_token=admin_token)
            if payload is not None:
                st.json(payload)

    st.divider()

    st.subheader("Logs")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        since_minutes = st.selectbox("since_minutes", options=[5, 15, 30, 60, 120, None], index=1)
    with c2:
        level = st.selectbox("level", options=["", "DEBUG", "INFO", "WARNING", "ERROR"], index=0)
    with c3:
        logs_limit = st.number_input("limit", min_value=10, max_value=500, value=100, step=10)
    with c4:
        show_logs = st.button("GET /utility/logs", type="primary")

    if show_logs:
        params: Dict[str, Any] = {"limit": int(logs_limit)}
        if since_minutes:
            params["since_minutes"] = int(since_minutes)
        if level:
            params["level"] = level
        payload = api.get("/utility/logs", params=params, admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    confirm_clear_logs = st.checkbox("confirm clear logs", value=False)
    if st.button("POST /utility/logs/clear", disabled=not confirm_clear_logs):
        payload = api.post("/utility/logs/clear", admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    st.divider()

    st.subheader("Traces")
    t1, t2 = st.columns(2)
    with t1:
        traces_limit = st.number_input("traces limit", min_value=1, max_value=200, value=20, step=5)
    with t2:
        traces_since = st.number_input("since_minutes (optional)", min_value=0, max_value=1440, value=0, step=5)

    if st.button("GET /utility/traces"):
        params: Dict[str, Any] = {"limit": int(traces_limit)}
        if traces_since:
            params["since_minutes"] = int(traces_since)
        payload = api.get("/utility/traces", params=params, admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    if st.button("GET /utility/traces/stats"):
        payload = api.get("/utility/traces/stats", admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    confirm_clear_traces = st.checkbox("confirm clear traces", value=False)
    if st.button("POST /utility/traces/clear", disabled=not confirm_clear_traces):
        payload = api.post("/utility/traces/clear", admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    st.divider()

    st.subheader("Reports (filesystem ./reports)")
    if st.button("GET /utility/reports/list"):
        payload = api.get("/utility/reports/list", admin_token=admin_token)
        if isinstance(payload, dict) and payload.get("reports"):
            st.json(payload)
        elif payload is not None:
            st.json(payload)

    filename = st.text_input("filename to delete (pdf)", value="")
    confirm_delete_pdf = st.checkbox("confirm delete file", value=False)
    if st.button("DELETE /utility/reports/{filename}", disabled=not (confirm_delete_pdf and filename.strip())):
        payload = api.delete(f"/utility/reports/{filename.strip()}", admin_token=admin_token)
        if payload is not None:
            st.json(payload)

    st.divider()

    st.subheader("Reports (Tarantool)")
    colr1, colr2 = st.columns([1, 3])
    with colr1:
        tar_limit = st.number_input("limit", min_value=5, max_value=200, value=20, step=5, key="tar_reports_limit")
    with colr2:
        tar_refresh = st.button("GET /reports", type="primary")

    if tar_refresh:
        payload = api.get("/reports", params={"limit": int(tar_limit), "offset": 0}, admin_token=admin_token)
        if payload is not None:
            st.session_state["tar_reports_cache"] = payload

    tar_payload = st.session_state.get("tar_reports_cache") or {}
    tar_reports = tar_payload.get("reports") or []
    if tar_reports:
        with st.expander("reports list", expanded=False):
            st.json(tar_payload)

        report_id = st.text_input("report_id to delete", value="")
        confirm_del = st.checkbox("confirm delete report", value=False)
        if st.button("DELETE /reports/{report_id}", disabled=not (confirm_del and report_id.strip())):
            resp = api.delete(f"/reports/{report_id.strip()}", admin_token=admin_token)
            if resp is not None:
                st.json(resp)

