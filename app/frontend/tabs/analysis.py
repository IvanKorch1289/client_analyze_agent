from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.formatters import format_ts, get_risk_emoji
from app.frontend.lib.ui import (
    render_metric_cards,
    section_header,
)
from app.frontend.lib.validators import validate_client_name, validate_inn


def _get_token() -> str:
    """Получить admin token из session_state."""
    return st.session_state.get("admin_token", "") or ""


def render(api: ApiClient) -> None:
    st.header("Анализ клиента")

    section = st.selectbox(
        "Выберите секцию",
        options=[
            "Запустить анализ сейчас",
            "Запланировать анализ",
            "Предыдущие анализы",
        ],
        index=0,
        key="analysis_section",
    )

    st.divider()

    if section == "Запустить анализ сейчас":
        _render_run_analysis_now(api)
    elif section == "Запланировать анализ":
        _render_schedule_analysis(api)
    elif section == "Предыдущие анализы":
        _render_previous_analyses(api)


def _render_run_analysis_now(api: ApiClient) -> None:
    section_header("Запустить анализ сейчас", emoji="🔍")

    with st.form("run_analysis_now"):
        col1, col2 = st.columns([2, 1])
        with col1:
            client_name = st.text_input("Название компании", placeholder="ООО Ромашка")
        with col2:
            inn = st.text_input("ИНН (опционально)", placeholder="7707083893", max_chars=12)
        additional_notes = st.text_area("Дополнительные заметки (опционально)", height=120)
        run_now = st.form_submit_button("Запустить", type="primary")

    if run_now:
        name_valid, name_err = validate_client_name(client_name)
        inn_valid, inn_err = validate_inn(inn, required=False)

        if not name_valid:
            st.error(f"❌ {name_err}")
        elif not inn_valid:
            st.error(f"❌ {inn_err}")
        else:
            payload = {
                "client_name": client_name.strip(),
                "inn": (inn or "").strip(),
                "additional_notes": (additional_notes or "").strip(),
            }
            with st.spinner("Запускаю анализ..."):
                result = api.post("/agent/analyze-client", json=payload, admin_token=_get_token())
            if result is not None:
                st.session_state["last_analysis_result"] = result

    last = st.session_state.get("last_analysis_result")
    if last:
        st.success("Анализ выполнен")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Статус", str(last.get("status", "")))
        with col2:
            st.metric("ID сессии", str(last.get("session_id", ""))[:32])
        with col3:
            report = last.get("report") or {}
            ra = report.get("risk_assessment") or {}
            st.metric("Риск-скор", ra.get("score", 0))
        with st.expander("Полный результат (JSON)"):
            st.json(last)


def _render_schedule_analysis(api: ApiClient) -> None:
    section_header("Запланировать анализ", emoji="⏰")
    
    when_mode = st.radio(
        "Когда выполнить",
        options=["delay_minutes", "delay_seconds", "run_date"],
        format_func=lambda x: {
            "delay_minutes": "Через N минут",
            "delay_seconds": "Через N секунд",
            "run_date": "В конкретную дату/время",
        }[x],
        horizontal=True,
        key="schedule_when_mode",
    )
    
    with st.form("schedule_analysis"):
        col1, col2 = st.columns([2, 1])
        with col1:
            sch_client_name = st.text_input("Название компании", key="sch_client_name")
        with col2:
            sch_inn = st.text_input("ИНН (обязательно)", key="sch_inn", max_chars=12)
        sch_notes = st.text_area("Дополнительные заметки (опционально)", key="sch_notes", height=100)

        delay_minutes = None
        delay_seconds = None
        run_date_iso = None

        if when_mode == "delay_minutes":
            delay_minutes = st.number_input("Задержка (мин)", min_value=1, value=5, step=1)
        elif when_mode == "delay_seconds":
            delay_seconds = st.number_input("Задержка (сек)", min_value=1, value=30, step=1)
        else:
            col_d, col_t = st.columns(2)
            with col_d:
                d = st.date_input("Дата", value=date.today(), min_value=date.today())
            with col_t:
                t = st.time_input("Время", value=datetime.now().time().replace(second=0, microsecond=0))
            run_dt = datetime.combine(d, t if isinstance(t, time) else time(0, 0))
            run_date_iso = run_dt.isoformat()
            if run_dt <= datetime.now():
                st.warning("⚠️ Выбранное время должно быть в будущем")

        schedule = st.form_submit_button("Запланировать", type="primary")

    if schedule:
        name_valid, name_err = validate_client_name(sch_client_name)
        inn_valid, inn_err = validate_inn(sch_inn, required=True)
        
        datetime_valid = True
        if when_mode == "run_date" and run_date_iso:
            scheduled_dt = datetime.fromisoformat(run_date_iso)
            if scheduled_dt <= datetime.now():
                datetime_valid = False

        if not name_valid:
            st.error(f"❌ {name_err}")
        elif not inn_valid:
            st.error(f"❌ {inn_err}")
        elif not datetime_valid:
            st.error("❌ Дата и время должны быть в будущем")
        else:
            payload: dict = {
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
                resp = api.post("/scheduler/schedule-analysis", json=payload, admin_token=_get_token())
            if resp is not None:
                st.success("✅ Запланировано")
                st.write(f"**ID задачи:** `{resp.get('task_id')}`")
                st.write(f"**Дата выполнения:** `{resp.get('run_date')}`")


def _render_previous_analyses(api: ApiClient) -> None:
    section_header("Предыдущие анализы", emoji="📊", help_text="Tarantool, TTL ~ 30 дней")

    if st.button("📊 Загрузить статистику", type="secondary"):
        with st.spinner("Загружаю статистику..."):
            stats_data = api.get("/reports/stats/summary", admin_token=_get_token())
        if stats_data is not None:
            st.session_state["reports_stats"] = stats_data

    stats = st.session_state.get("reports_stats") or {}
    if stats and stats.get("stats"):
        s = stats["stats"]
        metrics = {
            "Всего отчётов": s.get("total", 0),
            "Средний риск-скор": f"{s.get('avg_risk_score', 0):.1f}",
            "Высокий/Критический риск": s.get("by_risk_level", {}).get("high", 0)
            + s.get("by_risk_level", {}).get("critical", 0),
        }
        render_metric_cards(metrics, columns=3)

    st.divider()

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        limit = st.number_input("Показывать", min_value=5, max_value=200, value=20, step=5)
    with col2:
        risk_filter = st.selectbox("Фильтр по риску", options=["Все", "low", "medium", "high", "critical"])
    with col3:
        refresh = st.button("Обновить историю", type="primary")

    if refresh or "reports_cache" not in st.session_state:
        params: dict = {"limit": int(limit), "offset": 0}
        if risk_filter != "Все":
            params["risk_level"] = risk_filter
        with st.spinner("Загружаю список отчётов..."):
            payload = api.get("/reports", params=params, admin_token=_get_token())
        if payload is not None:
            st.session_state["reports_cache"] = payload

    reports_payload = st.session_state.get("reports_cache") or {}
    reports = reports_payload.get("reports") or []

    if not reports:
        st.info("Отчётов пока нет (или Tarantool в fallback режиме).")
        return

    st.markdown("**Список отчётов**")
    table_data = []
    for r in reports:
        risk_level = r.get("risk_level", "")
        table_data.append(
            {
                "Дата": format_ts(r.get("created_at")),
                "Компания": r.get("client_name", "")[:30],
                "ИНН": r.get("inn", ""),
                "Риск": f"{get_risk_emoji(risk_level)} {risk_level}",
                "Скор": r.get("risk_score", 0),
                "ID": r.get("report_id", "")[:16],
            }
        )
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    report_ids = [r.get("report_id", "") for r in reports if r.get("report_id")]
    if not report_ids:
        return

    selected_report_id = st.selectbox("Выберите отчёт для просмотра", options=report_ids, index=0)

    col_open, col_pdf = st.columns(2)
    with col_open:
        open_btn = st.button("Открыть детали", type="primary", use_container_width=True)
    with col_pdf:
        download_pdf_btn = st.button("📄 Скачать PDF", use_container_width=True)

    st.link_button(
        "📊 Экспорт CSV",
        api.url(f"/reports/{selected_report_id}/export?format=csv"),
    )

    if open_btn:
        with st.spinner("Загружаю отчёт..."):
            detail = api.get(f"/reports/{selected_report_id}", admin_token=_get_token())
        if detail is not None:
            st.session_state["opened_report"] = detail.get("report") if isinstance(detail, dict) else detail

    if download_pdf_btn:
        with st.spinner("Генерирую PDF..."):
            if (
                not st.session_state.get("opened_report")
                or st.session_state["opened_report"].get("report_id") != selected_report_id
            ):
                detail = api.get(f"/reports/{selected_report_id}", admin_token=_get_token())
                if detail is not None:
                    report_full = detail.get("report") if isinstance(detail, dict) else detail
                else:
                    st.error("❌ Не удалось загрузить отчёт")
                    report_full = None
            else:
                report_full = st.session_state["opened_report"]

            if report_full:
                report_data = report_full.get("report_data") or {}
                pdf_payload = {
                    "client_name": report_full.get("client_name", "") or report_data.get("metadata", {}).get("client_name", ""),
                    "inn": report_full.get("inn", "") or None,
                    "session_id": report_full.get("report_id", "") or None,
                    "report_data": report_data,
                }
                pdf_resp = api.post("/utility/reports/pdf", json=pdf_payload, admin_token=_get_token())
                if isinstance(pdf_resp, dict) and pdf_resp.get("status") == "success":
                    download_url = pdf_resp.get("download_url") or ""
                    if download_url:
                        st.success("✅ PDF отчёт сгенерирован!")
                        st.link_button(
                            "⬇️ Скачать PDF",
                            api.absolute_url(download_url),
                            type="primary",
                        )
                    else:
                        st.warning("⚠️ PDF создан, но ссылка на скачивание не получена")
                else:
                    st.error("❌ Ошибка при генерации PDF")

    opened = st.session_state.get("opened_report")
    if isinstance(opened, dict) and opened.get("report_id") == selected_report_id:
        _render_report_details(api, opened, selected_report_id)


def _render_report_details(api: ApiClient, opened: Dict[str, Any], selected_report_id: str) -> None:
    st.divider()
    st.subheader("📄 Детали отчёта")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Компания", opened.get("client_name", "N/A"))
    with col2:
        st.metric("ИНН", opened.get("inn") or "—")
    with col3:
        st.metric("Риск-скор", opened.get("risk_score", 0))

    report_data = opened.get("report_data") or {}

    if report_data.get("summary"):
        st.markdown("### 📝 Резюме")
        st.markdown(report_data.get("summary", ""))

    risk_assessment = report_data.get("risk_assessment") or {}
    if risk_assessment:
        st.markdown("### ⚠️ Оценка рисков")
        col_ra1, col_ra2, col_ra3 = st.columns(3)
        with col_ra1:
            st.metric("Скор", risk_assessment.get("score", 0))
        with col_ra2:
            level = risk_assessment.get("level", "unknown")
            st.metric("Уровень", f"{get_risk_emoji(level)} {level}")
        with col_ra3:
            st.metric("Факторов риска", len(risk_assessment.get("factors", [])))

        factors = risk_assessment.get("factors") or []
        if factors:
            with st.expander("📋 Факторы риска", expanded=False):
                for f in factors:
                    st.write(f"- {f}")

    with st.expander("📄 Генерация PDF отчёта", expanded=False):
        pdf_payload = {
            "client_name": opened.get("client_name", "") or report_data.get("metadata", {}).get("client_name", ""),
            "inn": opened.get("inn", "") or None,
            "session_id": opened.get("report_id", "") or None,
            "report_data": report_data,
        }
        if st.button("🖨️ Сгенерировать PDF отчёт", key="generate_pdf_from_details"):
            with st.spinner("Генерирую PDF отчёт..."):
                pdf_resp = api.post("/utility/reports/pdf", json=pdf_payload, admin_token=_get_token())
            if isinstance(pdf_resp, dict) and pdf_resp.get("status") == "success":
                download_url = pdf_resp.get("download_url") or ""
                if download_url:
                    st.success("✅ PDF отчёт успешно сгенерирован!")
                    st.link_button(
                        "⬇️ Скачать PDF файл",
                        api.absolute_url(download_url),
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.warning("⚠️ PDF создан, но ссылка на скачивание не получена")
            else:
                st.error("❌ Ошибка при генерации PDF")

    with st.expander("📋 Полные данные отчёта (JSON)", expanded=False):
        st.json(opened)

    st.divider()

    _render_feedback_section(api, opened, selected_report_id)


def _render_feedback_section(api: ApiClient, opened: Dict[str, Any], selected_report_id: str) -> None:
    st.subheader("📝 Фидбек и переанализ")
    st.markdown("**Если отчёт некорректен или LLM пропустила данные — отправьте фидбек:**")
    st.caption("Система перезапустит анализ с учётом ваших замечаний")
    
    feedback_rating = st.radio(
        "Оценка качества анализа",
        options=["accurate", "partially_accurate", "inaccurate"],
        format_func=lambda x: {
            "accurate": "✅ Точный — всё верно",
            "partially_accurate": "⚠️ Частично точный — есть неточности",
            "inaccurate": "❌ Неточный — много ошибок",
        }[x],
        horizontal=True,
        key=f"feedback_rating_{selected_report_id}",
        index=1,
    )
    
    feedback_comment = st.text_area(
        "Опишите проблему подробно",
        placeholder="Например: LLM не учла данные о судебных делах, пропущена информация о долгах в ФССП, неверно оценён риск по банкротству...",
        key=f"feedback_comment_{selected_report_id}",
        height=120,
    )
    
    focus_areas_options = [
        "Судебные дела",
        "Финансовое состояние",
        "Банкротство",
        "Исполнительные производства (ФССП)",
        "Госконтракты",
        "Аффилированность",
        "Репутация",
        "Учредители и руководство",
    ]
    focus_areas = st.multiselect(
        "На что обратить особое внимание при переанализе",
        options=focus_areas_options,
        key=f"focus_areas_{selected_report_id}",
    )
    
    rerun_checkbox = st.checkbox(
        "Перезапустить анализ с учётом фидбека",
        value=True,
        key=f"rerun_{selected_report_id}",
    )
    
    col_submit, col_status = st.columns([1, 2])
    with col_submit:
        submit_feedback = st.button(
            "🔄 Отправить фидбек" if rerun_checkbox else "💾 Сохранить фидбек",
            type="primary",
            key=f"submit_feedback_{selected_report_id}",
            use_container_width=True,
        )
    
    if submit_feedback:
        if feedback_rating in ("partially_accurate", "inaccurate") and not feedback_comment.strip():
            st.error("❌ Пожалуйста, опишите проблему в комментарии для переанализа")
        else:
            feedback_payload = {
                "report_id": selected_report_id,
                "rating": feedback_rating,
                "comment": feedback_comment.strip() if feedback_comment else None,
                "rerun_analysis": rerun_checkbox,
                "focus_areas": focus_areas if focus_areas else None,
            }
            
            with st.spinner("Отправляю фидбек и запускаю переанализ..." if rerun_checkbox else "Сохраняю фидбек..."):
                feedback_result = api.post("/agent/feedback", json=feedback_payload, admin_token=_get_token())
            
            if feedback_result is not None:
                status = feedback_result.get("status", "")
                
                if status == "reanalysis_complete":
                    st.success("✅ Переанализ выполнен с учётом вашего фидбека!")
                    new_session = feedback_result.get("new_session_id", "")
                    if new_session:
                        st.info(f"Новый ID сессии: `{new_session}`")
                    
                    if feedback_result.get("result"):
                        st.session_state["last_analysis_result"] = feedback_result["result"]
                    
                    st.balloons()
                    st.rerun()
                    
                elif status == "feedback_saved":
                    st.success("✅ Фидбек сохранён")
                    st.json(feedback_result.get("feedback", {}))
                else:
                    st.warning(f"Статус: {status}")
                    st.json(feedback_result)
