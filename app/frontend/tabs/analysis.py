from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.api_client import ApiClient


def _format_ts(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts or "")


def _valid_inn(inn: str) -> bool:
    inn = (inn or "").strip()
    if not inn:
        return True
    return inn.isdigit() and len(inn) in (10, 12)


def render(api: ApiClient) -> None:
    st.header("Анализ клиента")

    st.subheader("Запустить анализ сейчас")
    with st.form("run_analysis_now"):
        col1, col2 = st.columns([2, 1])
        with col1:
            client_name = st.text_input("Client name", placeholder="ООО Ромашка")
        with col2:
            inn = st.text_input("ИНН (опционально)", placeholder="7707083893", max_chars=12)
        additional_notes = st.text_area("Additional notes (опционально)", height=120)
        run_now = st.form_submit_button("Запустить", type="primary")

    if run_now:
        if not client_name.strip():
            st.error("client_name обязателен")
        elif not _valid_inn(inn):
            st.error("ИНН должен содержать 10 или 12 цифр")
        else:
            payload = {
                "client_name": client_name.strip(),
                "inn": (inn or "").strip(),
                "additional_notes": (additional_notes or "").strip(),
            }
            with st.spinner("Запускаю анализ..."):
                result = api.post("/agent/analyze-client", json=payload)
            if result is not None:
                st.session_state["last_analysis_result"] = result

    last = st.session_state.get("last_analysis_result")
    if last:
        st.success("Анализ выполнен")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("status", str(last.get("status", "")))
        with col2:
            st.metric("session_id", str(last.get("session_id", ""))[:32])
        with col3:
            report = last.get("report") or {}
            ra = report.get("risk_assessment") or {}
            st.metric("risk_score", ra.get("score", 0))
        with st.expander("Полный результат (JSON)"):
            st.json(last)

    st.divider()

    st.subheader("Запланировать анализ")
    with st.form("schedule_analysis"):
        col1, col2 = st.columns([2, 1])
        with col1:
            sch_client_name = st.text_input("Client name", key="sch_client_name")
        with col2:
            sch_inn = st.text_input("ИНН (обязательно)", key="sch_inn", max_chars=12)
        sch_notes = st.text_area("Additional notes (опционально)", key="sch_notes", height=100)

        when_mode = st.radio(
            "Когда выполнить",
            options=["delay_minutes", "delay_seconds", "run_date"],
            format_func=lambda x: {
                "delay_minutes": "Через N минут",
                "delay_seconds": "Через N секунд",
                "run_date": "В конкретную дату/время",
            }[x],
            horizontal=True,
        )

        delay_minutes = None
        delay_seconds = None
        run_date_iso = None

        if when_mode == "delay_minutes":
            delay_minutes = st.number_input("Задержка (мин)", min_value=1, value=5, step=1)
        elif when_mode == "delay_seconds":
            delay_seconds = st.number_input("Задержка (сек)", min_value=1, value=30, step=1)
        else:
            d = st.date_input("Дата", value=date.today())
            t = st.time_input("Время", value=datetime.now().time().replace(second=0, microsecond=0))
            run_dt = datetime.combine(d, t if isinstance(t, time) else time(0, 0))
            run_date_iso = run_dt.isoformat()

        schedule = st.form_submit_button("Запланировать", type="primary")

    if schedule:
        if not sch_client_name.strip():
            st.error("client_name обязателен")
        elif not sch_inn.strip():
            st.error("ИНН обязателен для планирования")
        elif not _valid_inn(sch_inn.strip()):
            st.error("ИНН должен содержать 10 или 12 цифр")
        else:
            payload = {
                "client_name": sch_client_name.strip(),
                "inn": sch_inn.strip(),
                "additional_notes": (sch_notes or "").strip(),
            }
            if delay_minutes is not None:
                payload["delay_minutes"] = int(delay_minutes)
            if delay_seconds is not None:
                payload["delay_seconds"] = int(delay_seconds)
            if run_date_iso is not None:
                payload["run_date"] = run_date_iso

            with st.spinner("Планирую задачу..."):
                resp = api.post("/scheduler/schedule-analysis", json=payload)
            if resp is not None:
                st.success("Запланировано")
                st.write(f"**task_id:** `{resp.get('task_id')}`")
                st.write(f"**run_date:** `{resp.get('run_date')}`")

    st.divider()

    st.subheader("Предыдущие анализы (Tarantool, TTL ~ 30 дней)")
    col1, col2 = st.columns([1, 3])
    with col1:
        limit = st.number_input("Показывать последних", min_value=5, max_value=200, value=20, step=5)
    with col2:
        refresh = st.button("Обновить историю", type="secondary")

    if refresh or "reports_cache" not in st.session_state:
        with st.spinner("Загружаю список отчётов..."):
            payload = api.get("/reports", params={"limit": int(limit), "offset": 0})
        if payload is not None:
            st.session_state["reports_cache"] = payload

    reports_payload = st.session_state.get("reports_cache") or {}
    reports = reports_payload.get("reports") or []

    if not reports:
        st.info("Отчётов пока нет (или Tarantool в fallback режиме).")
        return

    options = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for r in reports:
        rid = r.get("report_id", "")
        by_id[rid] = r
        title = f"{_format_ts(r.get('created_at'))} — {r.get('client_name','')} ({r.get('inn','')}) — {r.get('risk_level','')}/{r.get('risk_score',0)} — {rid[:8]}"
        options.append((title, rid))

    sel = st.selectbox(
        "Открыть отчёт",
        options=options,
        format_func=lambda x: x[0],
    )
    selected_report_id = sel[1]

    col_open, col_export_json, col_export_csv = st.columns([1, 1, 1])
    with col_open:
        open_btn = st.button("Открыть", type="primary")
    with col_export_json:
        st.link_button("Экспорт JSON", api.url(f"/reports/{selected_report_id}/export?format=json"))
    with col_export_csv:
        st.link_button("Экспорт CSV", api.url(f"/reports/{selected_report_id}/export?format=csv"))

    if open_btn:
        with st.spinner("Загружаю отчёт..."):
            detail = api.get(f"/reports/{selected_report_id}")
        if detail is not None:
            st.session_state["opened_report"] = detail.get("report") if isinstance(detail, dict) else detail

    opened = st.session_state.get("opened_report")
    if isinstance(opened, dict) and opened.get("report_id") == selected_report_id:
        st.divider()
        st.subheader("Отчёт")

        ra = (opened.get("report_data") or {}).get("risk_assessment") or {}
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("risk_level", opened.get("risk_level", ra.get("level", "unknown")))
        with m2:
            st.metric("risk_score", opened.get("risk_score", ra.get("score", 0)))
        with m3:
            st.metric("created_at", _format_ts(opened.get("created_at")))

        with st.expander("Кратко"):
            report_data = opened.get("report_data") or {}
            summary = report_data.get("summary") or ""
            if summary:
                st.markdown(summary)
            factors = (report_data.get("risk_assessment") or {}).get("factors") or []
            if factors:
                st.markdown("**Факторы риска:**")
                for f in factors[:15]:
                    st.write(f"- {f}")

        pdf_col1, pdf_col2 = st.columns([1, 3])
        with pdf_col1:
            gen_pdf = st.button("Сгенерировать PDF")
        with pdf_col2:
            st.caption("PDF генерируется через `/utility/reports/pdf` и сохраняется в `./reports`.")

        if gen_pdf:
            report_data = opened.get("report_data") or {}
            pdf_payload = {
                "client_name": opened.get("client_name", "") or report_data.get("metadata", {}).get("client_name", ""),
                "inn": opened.get("inn", "") or None,
                "session_id": opened.get("report_id", "") or None,
                "report_data": report_data,
            }
            with st.spinner("Генерирую PDF..."):
                pdf_resp = api.post("/utility/reports/pdf", json=pdf_payload)
            if isinstance(pdf_resp, dict) and pdf_resp.get("status") == "success":
                download_url = pdf_resp.get("download_url") or ""
                if download_url:
                    st.link_button("Скачать PDF", api.absolute_url(download_url))
                else:
                    st.info("PDF создан, но download_url не получен")

        with st.expander("Полный JSON"):
            st.json(opened)

