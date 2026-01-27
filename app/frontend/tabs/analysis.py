from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, time as time_type
from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.formatters import format_ts, get_risk_emoji
from app.frontend.lib.risk_charts import render_risk_summary
from app.frontend.lib.ui import (
    render_metric_cards,
    safe_api_call,
    section_header,
)
from app.frontend.lib.validators import validate_client_name, validate_inn

logger = logging.getLogger(__name__)

ANALYSIS_STEPS = [
    ("🔍 Сбор данных из источников...", 0.15),
    ("📊 Анализ финансовой информации...", 0.35),
    ("⚖️ Проверка судебных дел...", 0.55),
    ("🏛️ Проверка госконтрактов...", 0.70),
    ("🤖 Генерация отчёта с помощью ИИ...", 0.85),
    ("✅ Завершение анализа...", 0.95),
]

ESTIMATED_ANALYSIS_SECONDS = 45

# Маппинг этапов анализа к используемым моделям
STEP_MODEL_INFO = {
    "orchestrating": {
        "model": "Claude 3.5 Sonnet",
        "provider": "OpenRouter",
        "task": "Планирование поисковых запросов",
    },
    "collecting": {
        "model": "Perplexity + Tavily",
        "provider": "API",
        "task": "Сбор данных из веб-источников",
    },
    "searching": {
        "model": "Perplexity Sonar",
        "provider": "Perplexity AI",
        "task": "Веб-поиск и анализ",
    },
    "analyzing": {
        "model": "Claude 3.5 Sonnet",
        "provider": "OpenRouter",
        "task": "Анализ данных и оценка рисков",
    },
    "saving": {
        "model": "—",
        "provider": "File System",
        "task": "Сохранение отчёта",
    },
}


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
            _run_analysis_with_progress(api, payload)

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


def _run_analysis_with_progress(api: ApiClient, payload: Dict[str, Any]) -> None:
    """Run analysis with real-time streaming progress indicator and model info."""
    progress_container = st.empty()
    status_container = st.empty()
    model_info_container = st.empty()
    info_container = st.empty()
    cancel_button_container = st.empty()  # Контейнер для кнопки отмены

    start_time = time.time()
    result = None
    error_occurred = False

    try:
        import httpx

        # Используем streaming API для получения real-time прогресса
        url = api.url("/agent/analyze-client") + "?stream=true"
        headers = api._headers(admin_token=_get_token())
        headers["Accept"] = "text/event-stream"

        progress_container.progress(0.05, text="🚀 Запуск анализа...")

        with httpx.Client(timeout=180.0) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = response.text
                    raise Exception(f"API error {response.status_code}: {error_text}")

                current_step = ""
                current_progress = 0.05
                sources_info = ""

                for line in response.iter_lines():
                    if not line or not line.strip():
                        continue

                    # Парсинг SSE событий
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())

                            # Обработка различных типов событий
                            if event_type == "start":
                                session_id = data.get("session_id", "")
                                cancellable = data.get("cancellable", False)

                                info_container.caption(f"🔑 Session ID: `{session_id[:16]}...`")

                                # Показываем инструкцию по отмене если анализ можно отменить
                                if cancellable:
                                    cancel_button_container.info(
                                        "💡 **Для отмены анализа:** перейдите на вкладку **'📊 Мониторинг'** → **'🔄 Активные анализы'**"
                                    )

                            elif event_type == "progress":
                                step = data.get("step", "")
                                message = data.get("message", "")
                                progress_val = data.get("progress", 0) / 100.0
                                current_progress = progress_val

                                step_emoji = {
                                    "orchestrating": "🧠",
                                    "collecting": "📥",
                                    "searching": "🔍",
                                    "analyzing": "📊",
                                    "saving": "💾",
                                }.get(step, "⚙️")

                                current_step = f"{step_emoji} {message}"
                                progress_container.progress(progress_val, text=current_step)

                                elapsed = int(time.time() - start_time)

                                # Показываем информацию о модели для текущего этапа
                                model_info = STEP_MODEL_INFO.get(step, {})
                                if model_info:
                                    model_name = model_info.get("model", "")
                                    provider = model_info.get("provider", "")
                                    task = model_info.get("task", "")

                                    # Используем expander для компактного отображения в углу
                                    with model_info_container.container():
                                        st.caption(
                                            f"⏱️ **{elapsed} сек** | 🤖 **{model_name}** ({provider})\n\n📝 {task}"
                                        )
                                else:
                                    status_container.caption(f"⏱️ Время выполнения: {elapsed} сек | Этап: {step}")

                            elif event_type == "orchestrator":
                                intents_count = data.get("intents_count", 0)
                                intents = data.get("intents", [])
                                info_text = f"🎯 Сформировано запросов: {intents_count}"
                                if intents:
                                    info_text += f"\n\n📋 Категории: {', '.join(intents[:5])}"
                                info_container.info(info_text)

                            elif event_type == "data_collected":
                                sources = data.get("sources", [])
                                successful = data.get("successful", [])
                                duration_ms = data.get("duration_ms", 0)

                                sources_info = f"✅ Источники: {len(successful)}/{len(sources)}\n"
                                sources_info += f"📦 Успешно: {', '.join(successful)}"
                                info_container.success(sources_info)

                                current_progress = data.get("progress", 60) / 100.0
                                progress_container.progress(current_progress, text="📥 Данные собраны")

                                # Обновляем информацию о модели
                                with model_info_container.container():
                                    st.caption(
                                        f"⏱️ Сбор данных: {duration_ms / 1000:.1f} сек | "
                                        f"Источников: {len(successful)}/{len(sources)}"
                                    )

                            elif event_type == "source_preview":
                                # Sprint 2: Live Data Preview - показываем данные по мере поступления
                                sources_previews = data.get("sources", {})
                                successful_count = data.get("successful_count", 0)
                                total_count = data.get("total_count", 0)

                                if sources_previews:
                                    preview_text = (
                                        f"📊 **Предпросмотр данных** ({successful_count}/{total_count} источников):\n\n"
                                    )

                                    for (
                                        source_name,
                                        preview_data,
                                    ) in sources_previews.items():
                                        icon = preview_data.get("icon", "📄")
                                        preview = preview_data.get("preview", "")
                                        status = preview_data.get("status", "unknown")

                                        if status == "success":
                                            preview_text += f"{icon} **{source_name.upper()}**: {preview}\n\n"
                                        elif status == "error":
                                            preview_text += f"⚠️ **{source_name.upper()}**: {preview}\n\n"

                                    # Показываем в expander для компактности
                                    with info_container.expander(
                                        "📊 Предпросмотр данных (обновляется в реальном времени)",
                                        expanded=True,
                                    ):
                                        st.markdown(preview_text)

                            elif event_type == "analysis_progress":
                                # Sprint 2: Progressive analysis updates - показываем что LLM анализирует
                                substep = data.get("substep", "")
                                message = data.get("message", "")
                                progress_val = data.get("progress", 70) / 100.0
                                elapsed_seconds = data.get("elapsed_seconds", 0)

                                if substep == "llm_thinking":
                                    # Показываем что LLM думает с elapsed time
                                    info_container.info(
                                        f"🤔 **LLM анализ в процессе**\n\n{message}\n\n⏱️ Время анализа: {elapsed_seconds} сек"
                                    )
                                else:
                                    info_container.info(f"📊 {message}")

                                current_progress = progress_val
                                progress_container.progress(progress_val, text=f"🧠 {message}")

                            elif event_type == "report":
                                risk_score = data.get("risk_score", 0)
                                risk_level = data.get("risk_level", "unknown")
                                findings_count = data.get("findings_count", 0)

                                info_container.warning(
                                    f"⚠️ Риск-скор: **{risk_score}/100** ({risk_level})\n\n"
                                    f"📋 Обнаружено факторов: {findings_count}"
                                )

                                current_progress = data.get("progress", 85) / 100.0
                                progress_container.progress(current_progress, text="📊 Отчёт сформирован")

                            elif event_type == "result":
                                result = data
                                current_progress = 1.0
                                progress_container.progress(1.0, text="✅ Анализ завершён!")
                                elapsed = int(time.time() - start_time)

                                with model_info_container.container():
                                    st.caption(f"⏱️ **Общее время: {elapsed} сек** | ✅ **Завершено успешно**")

                            elif event_type == "error":
                                error_msg = data.get("error", "Неизвестная ошибка")
                                raise Exception(error_msg)

                            elif event_type == "cancelled":
                                cancel_button_container.empty()  # Убираем кнопку отмены
                                progress_container.empty()
                                status_container.empty()
                                model_info_container.empty()
                                info_container.warning("🛑 Анализ был отменён")
                                st.info("Вы можете запустить новый анализ в любое время")
                                return  # Выходим из функции

                            elif event_type == "complete":
                                cancel_button_container.empty()  # Убираем кнопку отмены
                                if result is None:
                                    # Если result не был получен ранее, делаем финальный запрос
                                    logger.warning("Stream completed without result event")

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse SSE data: {line}, error: {e}")
                            continue

    except Exception as e:
        error_occurred = True
        logger.error(f"Analysis error: {e}")
        cancel_button_container.empty()  # Убираем кнопку отмены при ошибке
        progress_container.empty()
        status_container.empty()
        model_info_container.empty()
        info_container.empty()
        st.error(f"❌ Ошибка при выполнении анализа: {str(e)}")
        st.info("💡 Попробуйте повторить запрос или обратитесь к администратору")

    if not error_occurred:
        if result is not None:
            st.session_state["last_analysis_result"] = result
        else:
            st.warning("⚠️ Анализ завершён, но финальные данные не получены. Попробуйте обновить страницу.")


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
                t = st.time_input(
                    "Время",
                    value=datetime.now().time().replace(second=0, microsecond=0),
                )
            run_dt = datetime.combine(d, t if isinstance(t, time_type) else time_type(0, 0))
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
                with safe_api_call("Планирование анализа"):
                    resp = api.post(
                        "/scheduler/schedule-analysis",
                        json=payload,
                        admin_token=_get_token(),
                    )
            if resp is not None:
                st.success("✅ Запланировано")
                st.write(f"**ID задачи:** `{resp.get('task_id')}`")
                st.write(f"**Дата выполнения:** `{resp.get('run_date')}`")


def _render_previous_analyses(api: ApiClient) -> None:
    section_header("Предыдущие анализы", emoji="📊", help_text="Tarantool, TTL ~ 30 дней")

    if st.button("📊 Загрузить статистику", type="secondary"):
        with st.spinner("Загружаю статистику..."):
            with safe_api_call("Загрузка статистики"):
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
            with safe_api_call("Загрузка списка отчётов"):
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
            with safe_api_call("Загрузка отчёта"):
                detail = api.get(f"/reports/{selected_report_id}", admin_token=_get_token())
        if detail is not None:
            st.session_state["opened_report"] = detail.get("report") if isinstance(detail, dict) else detail

    if download_pdf_btn:
        _handle_pdf_download(api, selected_report_id)

    opened = st.session_state.get("opened_report")
    if isinstance(opened, dict) and opened.get("report_id") == selected_report_id:
        _render_report_details(api, opened, selected_report_id)


def _handle_pdf_download(
    api: ApiClient,
    report_id: str,
    *,
    is_retry: bool = False,
    report_data_override: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Handle PDF download with error handling, retry option, and JSON fallback.

    Args:
        api: ApiClient instance
        report_id: ID of the report to download
        is_retry: Whether this is a retry attempt
        report_data_override: Optional pre-loaded report data
    """

    error_key = f"pdf_error_{report_id}"

    progress_container = st.empty()
    progress_container.progress(0.1, text="📄 Загрузка данных отчёта...")

    try:
        if report_data_override:
            report_full = report_data_override
        elif (
            not st.session_state.get("opened_report") or st.session_state["opened_report"].get("report_id") != report_id
        ):
            progress_container.progress(0.2, text="📥 Получение данных с сервера...")
            with safe_api_call("Загрузка отчёта для PDF", show_error=False, log_error=True):
                detail = api.get(f"/reports/{report_id}", admin_token=_get_token())
            if detail is not None:
                report_full = detail.get("report") if isinstance(detail, dict) else detail
            else:
                progress_container.empty()
                st.error("❌ Не удалось загрузить отчёт для генерации PDF")
                st.session_state[error_key] = "Ошибка загрузки данных отчёта"
                _show_pdf_error_actions(api, report_id, "Не удалось загрузить данные отчёта")
                return
        else:
            report_full = st.session_state["opened_report"]

        if not report_full:
            progress_container.empty()
            st.error("❌ Данные отчёта отсутствуют")
            _show_pdf_error_actions(api, report_id, "Данные отчёта отсутствуют")
            return

        progress_container.progress(0.5, text="🖨️ Генерация PDF...")

        report_data = report_full.get("report_data") or {}
        pdf_payload = {
            "client_name": report_full.get("client_name", "") or report_data.get("metadata", {}).get("client_name", ""),
            "inn": report_full.get("inn", "") or None,
            "session_id": report_full.get("report_id", "") or None,
            "report_data": report_data,
        }

        pdf_resp = None
        pdf_error = None

        try:
            pdf_resp = api.post("/utility/reports/pdf", json=pdf_payload, admin_token=_get_token())
        except Exception as e:
            pdf_error = str(e)
            logger.error(f"PDF generation error: {e}")

        progress_container.progress(0.9, text="📋 Обработка результата...")

        if pdf_resp is not None and isinstance(pdf_resp, dict) and pdf_resp.get("status") == "success":
            download_url = pdf_resp.get("download_url") or ""
            if download_url:
                progress_container.progress(1.0, text="✅ PDF готов!")
                time.sleep(0.3)
                progress_container.empty()

                st.success("✅ PDF отчёт сгенерирован!")
                st.link_button(
                    "⬇️ Скачать PDF",
                    api.absolute_url(download_url),
                    type="primary",
                )
                st.session_state.pop(error_key, None)
            else:
                progress_container.empty()
                st.warning("⚠️ PDF создан, но ссылка на скачивание не получена")
                _show_pdf_error_actions(api, report_id, "Ссылка на скачивание не получена", report_full)
        else:
            progress_container.empty()

            error_detail = "Неизвестная ошибка"
            if pdf_error:
                error_detail = pdf_error
            elif isinstance(pdf_resp, dict):
                error_detail = pdf_resp.get("message") or pdf_resp.get("detail") or str(pdf_resp)

            st.session_state[error_key] = error_detail

            st.error("❌ Ошибка при генерации PDF")
            _show_pdf_error_actions(api, report_id, error_detail, report_full)

    except Exception as e:
        progress_container.empty()
        error_msg = f"Непредвиденная ошибка: {str(e)}"
        logger.exception(f"Unexpected PDF error: {e}")
        st.error(f"❌ {error_msg}")
        st.session_state[error_key] = error_msg
        _show_pdf_error_actions(api, report_id, error_msg)


def _show_pdf_error_actions(
    api: ApiClient,
    report_id: str,
    error_detail: str,
    report_full: Optional[Dict[str, Any]] = None,
) -> None:
    """Show error details and action buttons for PDF failure."""
    with st.expander("🔍 Детали ошибки", expanded=False):
        st.code(error_detail, language="text")
        st.caption("Эта информация может быть полезна для технической поддержки")

    col_retry, col_json = st.columns(2)

    with col_retry:
        if st.button(
            "🔄 Повторить генерацию PDF",
            key=f"retry_pdf_{report_id}",
            use_container_width=True,
        ):
            _handle_pdf_download(api, report_id, is_retry=True, report_data_override=report_full)

    with col_json:
        if report_full:
            json_data = json.dumps(report_full, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 Скачать JSON (альтернатива)",
                data=json_data,
                file_name=f"report_{report_id[:16]}.json",
                mime="application/json",
                use_container_width=True,
                key=f"download_json_{report_id}",
            )
        else:
            st.info("JSON недоступен — отчёт не загружен")

    st.caption("💡 Если проблема повторяется, попробуйте экспортировать в CSV или обратитесь к администратору")


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
        # Визуализация риск-скора (Plotly charts)
        render_risk_summary(risk_assessment, show_factors_chart=True)

        st.divider()

        # Текстовые метрики
        st.markdown("### ⚠️ Детали оценки рисков")
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
            with st.expander("📋 Список факторов риска", expanded=False):
                for f in factors:
                    if isinstance(f, dict):
                        severity = f.get("severity", "")
                        description = f.get("description", str(f))
                        category = f.get("category", "")
                        emoji = {
                            "critical": "🔴",
                            "high": "🟠",
                            "medium": "🟡",
                            "low": "🟢",
                        }.get(severity, "⚪")
                        st.write(f"{emoji} **[{category}]** {description}")
                    else:
                        st.write(f"- {f}")

    with st.expander("📄 Генерация PDF отчёта", expanded=False):
        if st.button("🖨️ Сгенерировать PDF отчёт", key="generate_pdf_from_details"):
            _handle_pdf_download_from_details(api, opened, selected_report_id)

    with st.expander("📋 Полные данные отчёта (JSON)", expanded=False):
        st.json(opened)
        json_data = json.dumps(opened, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 Скачать JSON",
            data=json_data,
            file_name=f"report_{selected_report_id[:16]}.json",
            mime="application/json",
            key=f"download_json_details_{selected_report_id}",
        )

    st.divider()

    _render_feedback_section(api, opened, selected_report_id)


def _handle_pdf_download_from_details(
    api: ApiClient,
    opened: Dict[str, Any],
    report_id: str,
) -> None:
    """Handle PDF download from report details section with enhanced error handling."""
    progress_container = st.empty()
    progress_container.progress(0.2, text="🖨️ Подготовка данных...")

    report_data = opened.get("report_data") or {}
    pdf_payload = {
        "client_name": opened.get("client_name", "") or report_data.get("metadata", {}).get("client_name", ""),
        "inn": opened.get("inn", "") or None,
        "session_id": opened.get("report_id", "") or None,
        "report_data": report_data,
    }

    progress_container.progress(0.5, text="🖨️ Генерация PDF отчёта...")

    pdf_resp = None
    pdf_error = None

    try:
        with safe_api_call("Генерация PDF", show_error=False, log_error=True):
            pdf_resp = api.post("/utility/reports/pdf", json=pdf_payload, admin_token=_get_token())
    except Exception as e:
        pdf_error = str(e)
        logger.error(f"PDF generation error from details: {e}")

    progress_container.progress(0.9, text="📋 Обработка...")

    if pdf_resp is not None and isinstance(pdf_resp, dict) and pdf_resp.get("status") == "success":
        download_url = pdf_resp.get("download_url") or ""
        if download_url:
            progress_container.progress(1.0, text="✅ PDF готов!")
            time.sleep(0.3)
            progress_container.empty()

            st.success("✅ PDF отчёт успешно сгенерирован!")
            st.link_button(
                "⬇️ Скачать PDF файл",
                api.absolute_url(download_url),
                type="primary",
                use_container_width=True,
            )
        else:
            progress_container.empty()
            st.warning("⚠️ PDF создан, но ссылка на скачивание не получена")
            _show_pdf_error_actions(api, report_id, "Ссылка на скачивание не получена", opened)
    else:
        progress_container.empty()

        error_detail = "Неизвестная ошибка при генерации"
        if pdf_error:
            error_detail = pdf_error
        elif isinstance(pdf_resp, dict):
            error_detail = pdf_resp.get("message") or pdf_resp.get("detail") or str(pdf_resp)

        st.error("❌ Ошибка при генерации PDF")
        _show_pdf_error_actions(api, report_id, error_detail, opened)


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
                with safe_api_call("Отправка фидбека"):
                    feedback_result = api.post(
                        "/agent/feedback",
                        json=feedback_payload,
                        admin_token=_get_token(),
                    )

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
