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
    
    # Статистика
    stats_col1, stats_col2, stats_col3 = st.columns(3)
    if st.button("Загрузить статистику", type="secondary"):
        with st.spinner("Загружаю статистику..."):
            stats_data = api.get("/reports/stats/summary")
        if stats_data is not None:
            st.session_state["reports_stats"] = stats_data
    
    stats = st.session_state.get("reports_stats") or {}
    if stats and stats.get("stats"):
        s = stats["stats"]
        with stats_col1:
            st.metric("Всего отчётов", s.get("total", 0))
        with stats_col2:
            st.metric("Средний риск-скор", f"{s.get('avg_risk_score', 0):.1f}")
        with stats_col3:
            high_risk = s.get("by_risk_level", {}).get("high", 0) + s.get("by_risk_level", {}).get("critical", 0)
            st.metric("Высокий/Критический риск", high_risk)
    
    st.divider()
    
    # Фильтры и список
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        limit = st.number_input("Показывать", min_value=5, max_value=200, value=20, step=5)
    with col2:
        risk_filter = st.selectbox("Фильтр по риску", options=["Все", "low", "medium", "high", "critical"])
    with col3:
        refresh = st.button("Обновить историю", type="primary")

    if refresh or "reports_cache" not in st.session_state:
        params = {"limit": int(limit), "offset": 0}
        if risk_filter != "Все":
            params["risk_level"] = risk_filter
        with st.spinner("Загружаю список отчётов..."):
            payload = api.get("/reports", params=params)
        if payload is not None:
            st.session_state["reports_cache"] = payload

    reports_payload = st.session_state.get("reports_cache") or {}
    reports = reports_payload.get("reports") or []

    if not reports:
        st.info("Отчётов пока нет (или Tarantool в fallback режиме).")
        return

    # Таблица отчётов
    st.markdown("**Список отчётов**")
    table_data = []
    for r in reports:
        table_data.append({
            "Дата": _format_ts(r.get("created_at")),
            "Компания": r.get("client_name", "")[:30],
            "ИНН": r.get("inn", ""),
            "Риск": r.get("risk_level", ""),
            "Баллы": r.get("risk_score", 0),
            "ID": r.get("report_id", "")[:8],
        })
    
    # Выбор отчёта через клик на строку (эмуляция через radio)
    selected_idx = st.radio(
        "Выберите отчёт",
        options=range(len(table_data)),
        format_func=lambda i: f"{table_data[i]['Дата']} — {table_data[i]['Компания']} ({table_data[i]['ИНН']}) — {table_data[i]['Риск']}/{table_data[i]['Баллы']} — {table_data[i]['ID']}",
        label_visibility="collapsed"
    )
    
    selected_report_id = reports[selected_idx].get("report_id", "")

    col_open, col_export_json, col_export_csv = st.columns([1, 1, 1])
    with col_open:
        open_btn = st.button("Открыть детали", type="primary")
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
        st.subheader("📄 Детали отчёта")

        ra = (opened.get("report_data") or {}).get("risk_assessment") or {}
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            risk_level = opened.get("risk_level", ra.get("level", "unknown"))
            risk_colors = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
            st.metric("Уровень риска", f"{risk_colors.get(risk_level, '')} {risk_level.upper()}")
        with m2:
            st.metric("Риск-скор", f"{opened.get('risk_score', ra.get('score', 0))}/100")
        with m3:
            st.metric("Компания", opened.get("client_name", ""))
        with m4:
            st.metric("Дата", _format_ts(opened.get("created_at")))

        # Основная информация
        col_main, col_side = st.columns([2, 1])
        
        with col_main:
            with st.expander("📋 Краткое резюме", expanded=True):
                report_data = opened.get("report_data") or {}
                summary = report_data.get("summary") or ""
                if summary:
                    st.markdown(summary)
                else:
                    st.info("Резюме недоступно")
        
        with col_side:
            with st.expander("📊 Метаданные", expanded=True):
                metadata = (opened.get("report_data") or {}).get("metadata") or {}
                if metadata:
                    st.json(metadata)
                else:
                    st.write(f"**ИНН:** {opened.get('inn', 'N/A')}")
                    st.write(f"**ID:** {opened.get('report_id', '')[:16]}")

        # Факторы риска
        factors = (report_data.get("risk_assessment") or {}).get("factors") or []
        if factors:
            with st.expander("⚠️ Факторы риска", expanded=True):
                for i, f in enumerate(factors[:15], 1):
                    st.markdown(f"{i}. {f}")
                if len(factors) > 15:
                    st.caption(f"... и ещё {len(factors) - 15} факторов")

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

