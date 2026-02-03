from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.formatters import format_ts, get_status_emoji
from app.frontend.lib.ui import (
    confirm_action,
    render_payload,
    section_header,
)


def _bool_param(val: bool) -> str:
    return "true" if val else "false"


# Backward compatibility alias
def _format_ts(ts: Any) -> str:
    return format_ts(ts)


def render(api: ApiClient, *, admin_token: str) -> None:
    st.header("⚙️ Утилиты (admin)")

    st.info("🔒 Эта вкладка доступна только в админ-режиме. Destructive операции требуют подтверждения.")

    # Навигация по секциям
    section = st.selectbox(
        "Выберите секцию",
        options=[
            "Здоровье и конфигурация",
            "Автоматы защиты и метрики",
            "Кэш и Tarantool",
            "Внешние сервисы",
            "Логи и трассировки",
            "Управление отчётами",
            "🔒 Тестирование PII маскирования",
        ],
        index=0,
    )

    st.divider()

    if section == "Здоровье и конфигурация":
        _render_health_config(api, admin_token)
    elif section == "Автоматы защиты и метрики":
        _render_circuit_metrics(api, admin_token)
    elif section == "Кэш и Tarantool":
        _render_cache_tarantool(api, admin_token)
    elif section == "Внешние сервисы":
        _render_external_services(api, admin_token)
    elif section == "Логи и трассировки":
        _render_logs_traces(api, admin_token)
    elif section == "Управление отчётами":
        _render_reports_management(api, admin_token)
    elif section == "🔒 Тестирование PII маскирования":
        _render_pii_masking(api, admin_token)


def _render_health_config(api: ApiClient, admin_token: str) -> None:
    st.subheader("🏥 Здоровье и конфигурация")

    deep = st.checkbox("deep=true (реальные проверки внешних сервисов)", value=False)
    if st.button("🔍 Проверить /utility/health", type="primary"):
        payload = api.get(
            "/utility/health",
            params={"deep": _bool_param(deep)},
            admin_token=admin_token,
        )
        if payload is not None:
            status = payload.get("status", "unknown")
            if status == "healthy":
                st.success(f"✅ Статус: {status}")
            else:
                st.warning(f"⚠️ Статус: {status}")

            issues = payload.get("issues")
            if issues:
                st.error("Проблемы:")
                for issue in issues:
                    st.write(f"- {issue}")

            with st.expander("Детали компонентов", expanded=False):
                st.json(payload.get("components", {}))

    st.divider()
    st.markdown("### ⚙️ Конфигурация")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("📄 Снимок /utility/config"):
            cfg = api.get("/utility/config", admin_token=admin_token)
            if cfg is not None:
                st.session_state["utility_config_snapshot"] = cfg
    with col2:
        confirm_reload = st.checkbox("✅ Подтвердить перезагрузку", value=False)
        if st.button("🔄 Перезагрузить конфиг", disabled=not confirm_reload):
            resp = api.post("/utility/config/reload", admin_token=admin_token)
            if resp is not None:
                st.success("Конфигурация перезагружена")
                st.json(resp)

    cfg_snapshot = st.session_state.get("utility_config_snapshot")
    if cfg_snapshot:
        with st.expander("📋 Config snapshot", expanded=False):
            st.json(cfg_snapshot)


def _render_circuit_metrics(api: ApiClient, admin_token: str) -> None:
    st.subheader("🔌 Автоматы защиты и метрики")

    st.markdown("### 🔌 Главный автомат защиты")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Статус главного CB"):
            payload = api.get("/utility/app-circuit-breaker", admin_token=admin_token)
            if payload is not None:
                state = payload.get("state", "unknown")
                if state == "closed":
                    st.success(f"✅ Состояние: {state}")
                else:
                    st.warning(f"⚠️ Состояние: {state}")
                st.json(payload)
    with c2:
        confirm_reset_app = st.checkbox("✅ Подтвердить сброс главного CB", value=False)
        if st.button("🔄 Сбросить главный CB", disabled=not confirm_reset_app):
            payload = api.post("/utility/app-circuit-breaker/reset", admin_token=admin_token)
            if payload is not None:
                st.success("Главный автомат защиты сброшен")
                st.json(payload)

    st.markdown("### 🔌 Автоматы защиты сервисов")
    if st.button("📊 Загрузить статус всех CB"):
        cb = api.get("/utility/circuit-breakers", admin_token=admin_token)
        if cb is not None:
            st.session_state["cb_status"] = cb

    cb = st.session_state.get("cb_status")
    if cb is not None:
        # ИСПРАВЛЕНИЕ: backend возвращает circuit_breakers, не breakers
        breakers = cb.get("circuit_breakers", {})
        if breakers:
            # Показать статус каждого CB
            cols = st.columns(min(len(breakers), 4))
            for idx, (name, status) in enumerate(breakers.items()):
                with cols[idx % len(cols)]:
                    state = status.get("state", "unknown") if isinstance(status, dict) else "unknown"
                    emoji = get_status_emoji(state)
                    if state == "closed":
                        st.success(f"{emoji} {name}")
                    elif state == "open":
                        st.error(f"{emoji} {name}")
                    else:
                        st.warning(f"{emoji} {name}")

        with st.expander("📋 Детали всех CB", expanded=False):
            st.json(cb)

        services = sorted(breakers.keys()) if breakers else ["perplexity", "tavily", "openrouter"]
        service = st.selectbox("Выбрать сервис для сброса", options=services, index=0)
        if confirm_action("cb_confirm_service_reset", "Подтвердить сброс CB"):
            if st.button("🔄 Сбросить circuit breaker"):
                payload = api.post(
                    f"/utility/circuit-breakers/{service}/reset",
                    admin_token=admin_token,
                )
                if payload is not None:
                    st.success(f"Автомат защиты для {service} сброшен")
                    st.json(payload)

    st.divider()
    st.markdown("### 📊 Метрики")

    colm1, colm2, colm3 = st.columns(3)
    with colm1:
        if st.button("📈 Метрики HTTP клиента"):
            payload = api.get("/utility/metrics", admin_token=admin_token)
            if payload is not None:
                st.session_state["utility_metrics"] = payload
    with colm2:
        if st.button("📈 Метрики приложения"):
            payload = api.get("/utility/app-metrics", admin_token=admin_token)
            if payload is not None:
                st.session_state["utility_app_metrics"] = payload
    with colm3:
        st.caption("Сброс метрик")

    if st.session_state.get("utility_metrics"):
        with st.expander("📊 Метрики HTTP клиента", expanded=False):
            st.json(st.session_state["utility_metrics"])

    if st.session_state.get("utility_app_metrics"):
        with st.expander("📊 Метрики приложения", expanded=False):
            st.json(st.session_state["utility_app_metrics"])

    col_reset1, col_reset2 = st.columns(2)
    with col_reset1:
        confirm_reset_metrics = st.checkbox("✅ Подтвердить сброс метрик HTTP", value=False)
        if st.button("🔄 Сбросить метрики HTTP", disabled=not confirm_reset_metrics):
            payload = api.post("/utility/metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.success("Метрики HTTP сброшены")
                st.json(payload)
    with col_reset2:
        confirm_reset_app_metrics = st.checkbox("✅ Подтвердить сброс метрик приложения", value=False)
        if st.button("🔄 Сбросить метрики приложения", disabled=not confirm_reset_app_metrics):
            payload = api.post("/utility/app-metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.success("Метрики приложения сброшены")
                st.json(payload)


def _render_cache_tarantool(api: ApiClient, admin_token: str) -> None:
    st.subheader("💾 Кэш и Tarantool")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🗄️ Tarantool status"):
            payload = api.get("/utility/tarantool/status", admin_token=admin_token)
            if payload is not None:
                mode = payload.get("mode", "unknown")
                if mode == "tarantool":
                    st.success(f"✅ Режим: {mode}")
                else:
                    st.warning(f"⚠️ Режим: {mode} (fallback)")
                st.json(payload)
    with c2:
        if st.button("📊 Cache metrics"):
            payload = api.get("/utility/cache/metrics", admin_token=admin_token)
            if payload is not None:
                st.session_state["utility_cache_metrics"] = payload
    with c3:
        confirm_cache_metrics_reset = st.checkbox("✅ Подтвердить сброс метрик кэша", value=False)
        if st.button("🔄 Сбросить метрики кэша", disabled=not confirm_cache_metrics_reset):
            payload = api.post("/utility/cache/metrics/reset", admin_token=admin_token)
            if payload is not None:
                st.success("Метрики кэша сброшены")
                st.json(payload)

    if st.session_state.get("utility_cache_metrics"):
        with st.expander("📊 Cache Metrics", expanded=False):
            st.json(st.session_state["utility_cache_metrics"])

    st.divider()
    st.markdown("### 🔍 Cache Entries")

    limit = st.number_input("Количество записей", min_value=1, max_value=100, value=10)
    if st.button("📋 Показать /utility/cache/entries"):
        payload = api.get(
            "/utility/cache/entries",
            params={"limit": int(limit)},
            admin_token=admin_token,
        )
        if payload is not None:
            entries = payload.get("entries", [])
            if entries:
                st.success(f"Найдено записей: {len(entries)}")
                for entry in entries:
                    with st.expander(f"🔑 {entry.get('key', 'N/A')}", expanded=False):
                        st.json(entry)
            else:
                st.info("Нет записей в кэше")

    st.divider()
    st.markdown("### 🗑️ Удаление по префиксу")

    prefix = st.text_input("Префикс (например: search:)", value="search:")
    confirm_prefix = st.checkbox("✅ Подтвердить удаление по префиксу", value=False)
    if st.button("🗑️ Удалить по префиксу", disabled=not confirm_prefix):
        payload = api.delete(f"/utility/cache/prefix/{prefix}", admin_token=admin_token)
        if payload is not None:
            msg = payload.get("message", "")
            st.success(msg if msg else "Записи удалены")
            st.json(payload)


def _render_external_services(api: ApiClient, admin_token: str) -> None:
    st.subheader("🌐 Внешние сервисы")

    section_header("Статус сервисов", emoji="📊")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        if st.button("🔮 Perplexity"):
            payload = api.get("/utility/perplexity/status", admin_token=admin_token)
            if payload is not None:
                # ИСПРАВЛЕНИЕ: использовать available вместо configured
                available = payload.get("available", False)
                if available:
                    st.success("✅ Доступен")
                else:
                    st.error("❌ Недоступен")
                render_payload(payload, title="Детали Perplexity", show_status=False)
    with s2:
        if st.button("🔍 Tavily"):
            payload = api.get("/utility/tavily/status", admin_token=admin_token)
            if payload is not None:
                available = payload.get("available", False)
                if available:
                    st.success("✅ Доступен")
                else:
                    st.error("❌ Недоступен")
                render_payload(payload, title="Детали Tavily", show_status=False)
    with s3:
        if st.button("🤖 OpenRouter"):
            payload = api.get("/utility/openrouter/status", admin_token=admin_token)
            if payload is not None:
                # ИСПРАВЛЕНИЕ: OpenRouter использует available
                available = payload.get("available", False)
                if available:
                    st.success("✅ Доступен")
                else:
                    st.error("❌ Недоступен")
                render_payload(payload, title="Детали OpenRouter", show_status=False)
    with s4:
        if st.button("📧 Email"):
            payload = api.get("/utility/email/status", admin_token=admin_token)
            if payload is not None:
                configured = payload.get("configured", False)
                if configured:
                    st.success("✅ Настроен")
                else:
                    st.error("❌ Не настроен")
                render_payload(payload, title="Детали Email", show_status=False)

    st.divider()
    section_header("Очистка кэша сервисов", emoji="🗑️")

    clear1, clear2 = st.columns(2)
    with clear1:
        if confirm_action("confirm_tavily_cache_clear", "Подтвердить очистку кэша Tavily"):
            if st.button("🗑️ Очистить кэш Tavily"):
                payload = api.post("/utility/tavily/cache/clear", admin_token=admin_token)
                if payload is not None:
                    st.success("Кэш Tavily очищен")
                    st.json(payload)
    with clear2:
        if confirm_action("confirm_perplexity_cache_clear", "Подтвердить очистку кэша Perplexity"):
            if st.button("🗑️ Очистить кэш Perplexity"):
                payload = api.post("/utility/perplexity/cache/clear", admin_token=admin_token)
                if payload is not None:
                    st.success("Кэш Perplexity очищен")
                    st.json(payload)


def _render_logs_traces(api: ApiClient, admin_token: str) -> None:
    st.subheader("📝 Логи и трассировки")

    section_header("Logs", emoji="📝")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        since_minutes = st.selectbox("За последние (мин)", options=[5, 15, 30, 60, 120, None], index=1)
    with c2:
        level = st.selectbox("Уровень", options=["Все", "DEBUG", "INFO", "WARNING", "ERROR"], index=0)
    with c3:
        logs_limit = st.number_input("Лимит", min_value=10, max_value=500, value=100, step=10)
    with c4:
        show_logs = st.button("📋 Загрузить логи", type="primary")

    if show_logs:
        params: Dict[str, Any] = {"limit": int(logs_limit)}
        if since_minutes:
            params["since_minutes"] = int(since_minutes)
        if level and level != "Все":
            params["level"] = level
        payload = api.get("/utility/logs", params=params, admin_token=admin_token)
        if payload is not None:
            logs = payload.get("logs", [])
            if logs:
                st.success(f"Найдено логов: {len(logs)}")
                with st.expander("📋 Логи", expanded=True):
                    for log in logs[:50]:  # Показываем первые 50
                        level_emoji = {
                            "DEBUG": "🔍",
                            "INFO": "ℹ️",
                            "WARNING": "⚠️",
                            "ERROR": "❌",
                        }.get(log.get("level", ""), "📝")
                        st.text(f"{level_emoji} [{log.get('timestamp', '')}] {log.get('message', '')}")
            else:
                st.info("Логов не найдено")

    if st.button("📊 Статистика логов"):
        payload = api.get("/utility/logs/stats", admin_token=admin_token)
        if payload is not None:
            render_payload(payload, title="Статистика логов")

    if confirm_action("confirm_clear_logs", "Подтвердить очистку логов"):
        if st.button("🗑️ Очистить логи"):
            payload = api.post("/utility/logs/clear", admin_token=admin_token)
            if payload is not None:
                st.success("Логи очищены")
                st.json(payload)

    st.divider()
    section_header("Traces (Spans)", emoji="🔍")

    t1, t2, t3 = st.columns(3)
    with t1:
        traces_limit = st.number_input("Лимит трейсов", min_value=1, max_value=200, value=20, step=5)
    with t2:
        traces_since = st.number_input(
            "За последние (мин)",
            min_value=0,
            max_value=1440,
            value=0,
            step=5,
            key="traces_since",
        )
    with t3:
        st.caption("Опции")

    if st.button("📋 Загрузить трейсы"):
        params: Dict[str, Any] = {"limit": int(traces_limit)}
        if traces_since:
            params["since_minutes"] = int(traces_since)
        payload = api.get("/utility/traces", params=params, admin_token=admin_token)
        if payload is not None:
            # ИСПРАВЛЕНИЕ: backend возвращает spans, не traces
            spans = payload.get("spans", [])
            if spans:
                st.success(f"Найдено трейсов: {len(spans)}")
                with st.expander("🔍 Трейсы (Spans)", expanded=False):
                    st.json(payload)
            else:
                st.info("Трейсов не найдено")

    if st.button("📊 Статистика трейсов"):
        payload = api.get("/utility/traces/stats", admin_token=admin_token)
        if payload is not None:
            render_payload(payload, title="Статистика трейсов")

    if confirm_action("confirm_clear_traces", "Подтвердить очистку трейсов"):
        if st.button("🗑️ Очистить трейсы"):
            payload = api.post("/utility/traces/clear", admin_token=admin_token)
            if payload is not None:
                st.success("Трейсы очищены")
                st.json(payload)


def _render_reports_management(api: ApiClient, admin_token: str) -> None:
    st.subheader("📄 Управление отчётами")

    st.markdown("### 📁 Reports (Filesystem ./reports)")
    if st.button("📋 Список PDF отчётов"):
        payload = api.get("/utility/reports/list", admin_token=admin_token)
        if isinstance(payload, dict):
            reports = payload.get("reports", [])
            if reports:
                st.success(f"Найдено файлов: {len(reports)}")
                for report in reports:
                    with st.expander(f"📄 {report.get('filename', 'N/A')}", expanded=False):
                        st.write(f"**Размер:** {report.get('size_bytes', 0)} байт")
                        st.write(f"**Создан:** {_format_ts(report.get('created', 0))}")
                        if report.get("download_url"):
                            st.link_button("⬇️ Скачать", api.absolute_url(report["download_url"]))
            else:
                st.info("PDF отчётов нет")
        elif payload is not None:
            st.json(payload)

    st.divider()
    st.markdown("### 🗑️ Удаление PDF файла")

    filename = st.text_input("Имя файла (например: report_123.pdf)", value="")
    confirm_delete_pdf = st.checkbox("✅ Подтвердить удаление PDF", value=False)
    if st.button("🗑️ Удалить PDF файл", disabled=not (confirm_delete_pdf and filename.strip())):
        payload = api.delete(f"/utility/reports/{filename.strip()}", admin_token=admin_token)
        if payload is not None:
            st.success(f"Файл {filename} удалён")
            st.json(payload)

    st.divider()
    st.markdown("### 🗄️ Reports (Tarantool)")

    colr1, colr2 = st.columns([1, 3])
    with colr1:
        tar_limit = st.number_input(
            "Лимит",
            min_value=5,
            max_value=200,
            value=20,
            step=5,
            key="tar_reports_limit",
        )
    with colr2:
        tar_refresh = st.button("📋 Загрузить из Tarantool", type="primary")

    if tar_refresh:
        payload = api.get(
            "/reports",
            params={"limit": int(tar_limit), "offset": 0},
            admin_token=admin_token,
        )
        if payload is not None:
            st.session_state["tar_reports_cache"] = payload

    tar_payload = st.session_state.get("tar_reports_cache") or {}
    tar_reports = tar_payload.get("reports") or []
    if tar_reports:
        st.success(f"Найдено отчётов: {len(tar_reports)}")
        with st.expander("📋 Список отчётов", expanded=False):
            for r in tar_reports[:10]:  # Показываем первые 10
                st.write(
                    f"- **{r.get('client_name', 'N/A')}** (ИНН: {r.get('inn', 'N/A')}) — {r.get('report_id', '')[:16]}"
                )

        st.divider()
        st.markdown("### 🗑️ Удаление отчёта из Tarantool")

        report_id = st.text_input("report_id для удаления", value="")
        confirm_del = st.checkbox("✅ Подтвердить удаление отчёта", value=False)
        if st.button("🗑️ Удалить отчёт", disabled=not (confirm_del and report_id.strip())):
            resp = api.delete(f"/reports/{report_id.strip()}", admin_token=admin_token)
            if resp is not None:
                st.success(f"Отчёт {report_id} удалён")
                st.json(resp)
    else:
        st.info("Отчётов в Tarantool нет или не загружены")


def _render_pii_masking(api: ApiClient, admin_token: str) -> None:
    """Интерфейс для тестирования маскирования PII данных."""
    st.subheader("🔒 Тестирование PII маскирования")

    st.info(
        """
        **Reversible Pseudonymization** - маскирование персональных данных перед отправкой в LLM.

        Система автоматически заменяет PII данные на нумерованные псевдонимы:
        - ИНН: `7707083893` → `[INN_1]`
        - ФИО: `Иванов Иван Иванович` → `[CLIENT_NAME_1]`
        - Телефон: `+7(499)123-45-67` → `[PHONE_1]`
        - Email: `test@example.com` → `[EMAIL_1]`

        После получения ответа от LLM данные автоматически восстанавливаются.
        """
    )

    st.divider()

    # Форма для ввода текста
    st.markdown("### 📝 Тест маскирования")

    # Примеры текста
    example_texts = {
        "Пример 1: Компания": "ООО 'Рога и Копыта', ИНН 7707083893, ОГРН 1027700132195, "
        "генеральный директор Иванов Иван Иванович, телефон +7(499)123-45-67, email test@example.com",
        "Пример 2: Физлицо": "Петров Петр Петрович, паспорт 45 03 123456, СНИЛС 123-456-789-01, "
        "тел 8(916)765-43-21, адрес: г. Москва, ул. Ленина, д. 1",
        "Пример 3: Смешанный": "Компания Ромашка (ИНН 1234567890) под руководством Сидорова С.С. "
        "находится по адресу 101000, г. Москва, ул. Мясницкая, д. 13. Контакты: +7(495)111-22-33",
        "Свой текст": "",
    }

    selected_example = st.selectbox(
        "Выберите пример или введите свой текст:",
        options=list(example_texts.keys()),
        index=0,
    )

    default_text = example_texts[selected_example]
    input_text = st.text_area(
        "Текст для маскирования:",
        value=default_text,
        height=150,
        placeholder="Введите текст с персональными данными...",
    )

    col1, col2 = st.columns(2)
    with col1:
        mask_level = st.selectbox(
            "Уровень маскирования:",
            options=["high", "medium", "low"],
            index=0,
            help="low: только ИНН/ОГРН/карты\nmedium: + телефоны/email\nhigh: все PII включая ФИО",
        )
    with col2:
        language = st.selectbox(
            "Язык текста:",
            options=["ru", "en"],
            index=0,
        )

    if st.button("🔒 Замаскировать текст", type="primary", disabled=not input_text.strip()):
        with st.spinner("Маскирование..."):
            payload = api.post(
                "/llm/mask-text",
                json={
                    "text": input_text,
                    "language": language,
                    "mask_level": mask_level,
                },
                admin_token=admin_token,
            )

            if payload is not None:
                st.success("✅ Маскирование выполнено!")

                # Метрики
                pii_detected = payload.get("pii_detected", False)
                pii_count = payload.get("pii_count", 0)
                detected_types = payload.get("detected_pii_types", [])

                if pii_detected:
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        st.metric("Найдено PII:", pii_count)
                    with col_m2:
                        st.metric("Типов данных:", len(detected_types))

                    if detected_types:
                        st.info(f"**Обнаруженные типы PII:** {', '.join(detected_types)}")
                else:
                    st.warning("⚠️ PII данные не обнаружены в тексте")

                # Показываем результаты
                st.markdown("### 📤 Оригинальный текст:")
                st.code(payload.get("original_text", ""), language="text")

                st.markdown("### 🔒 Замаскированный текст (отправляется в LLM):")
                st.code(payload.get("masked_text", ""), language="text")

                # Показываем маппинг
                replacements = payload.get("replacements", [])
                if replacements:
                    with st.expander("🔑 Маппинг для размаскирования", expanded=False):
                        st.json(replacements)

                    # Объяснение
                    st.markdown("### ℹ️ Как это работает:")
                    st.markdown(
                        """
                        1. **Маскирование**: Перед отправкой в LLM все PII данные заменяются на нумерованные псевдонимы
                        2. **Обработка**: LLM видит только псевдонимы, реальные данные защищены
                        3. **Размаскирование**: После получения ответа псевдонимы автоматически заменяются обратно

                        **Преимущества:**
                        - ✅ Защита персональных данных при обращении к внешним LLM
                        - ✅ Полная обратимость (в отличие от хеширования)
                        - ✅ Сохранение контекста для LLM (псевдонимы читаемые)
                        - ✅ Соответствие 152-ФЗ и GDPR
                        """
                    )
            else:
                st.error("❌ Ошибка маскирования. Проверьте логи.")

    st.divider()

    # Предупреждение о безопасности
    st.warning(
        """
        ⚠️ **ВАЖНО:**
        Маскирование работает автоматически для всех обращений к внешним LLM.
        Эта страница предназначена только для тестирования и preview.
        """
    )
