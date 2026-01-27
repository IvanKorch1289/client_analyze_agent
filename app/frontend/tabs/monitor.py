from __future__ import annotations

import time

import streamlit as st

from app.frontend.api_client import ApiClient


def render(api: ApiClient, *, admin_token: str) -> None:
    """
    Системный монитор - мониторинг производительности и здоровья системы в реальном времени.

    Использует admin endpoints:
    - GET /admin/cache/stats - Статистика кэша
    - GET /admin/llm/stats - Статистика LLM вызовов
    - GET /admin/health/detailed - Детальная проверка здоровья
    - GET /admin/metrics/system - Системные метрики (CPU, память)
    """
    st.header("📊 Системный монитор")

    st.info("🔒 Мониторинг системы в реальном времени. Обновление по запросу.")

    # Auto-refresh опция
    auto_refresh = st.checkbox("🔄 Автообновление каждые 5 секунд", value=False)

    if auto_refresh:
        if "last_refresh" not in st.session_state:
            st.session_state["last_refresh"] = time.time()

        elapsed = time.time() - st.session_state["last_refresh"]
        if elapsed >= 5:
            st.session_state["last_refresh"] = time.time()
            st.rerun()

        st.caption(f"⏱️ Следующее обновление через {5 - int(elapsed)} сек")

    # Кнопка ручного обновления
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Обновить", type="primary"):
            st.session_state["last_refresh"] = time.time()
            st.rerun()

    st.divider()

    # Секции мониторинга
    tabs = st.tabs(
        [
            "🔄 Активные анализы",
            "📈 Системные метрики",
            "🧠 Статистика LLM",
            "💾 Статистика кэша",
            "🏥 Статус здоровья",
        ]
    )

    with tabs[0]:
        _render_running_analyses(api, admin_token)

    with tabs[1]:
        _render_system_metrics(api, admin_token)

    with tabs[2]:
        _render_llm_statistics(api, admin_token)

    with tabs[3]:
        _render_cache_statistics(api, admin_token)

    with tabs[4]:
        _render_health_status(api, admin_token)


def _render_running_analyses(api: ApiClient, admin_token: str) -> None:
    """Управление активными анализами клиентов."""
    st.subheader("🔄 Активные анализы")

    st.info("Здесь отображаются все запущенные анализы. Вы можете отменить любой запущенный анализ.")

    try:
        response = api.get("/agent/analyze/running", admin_token=admin_token)

        if not response:
            st.warning("⚠️ Не удалось получить список активных анализов")
            return

        running = response.get("running", [])
        total = response.get("total_running", 0)

        if total == 0:
            st.success("✅ Нет активных анализов в данный момент")
            return

        st.metric("Активных анализов", total)
        st.divider()

        # Отображаем каждый активный анализ с кнопкой отмены
        for analysis in running:
            session_id = analysis.get("session_id", "unknown")
            client_name = analysis.get("client_name", "Неизвестный клиент")
            started_at = analysis.get("started_at", "")
            duration = analysis.get("duration_seconds", 0)

            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])

                with col1:
                    st.write(f"**{client_name}**")
                    st.caption(f"Session: `{session_id[:16]}...`")

                with col2:
                    if started_at:
                        st.caption(f"Запущен: {started_at}")
                    st.caption(f"Длительность: {duration} сек")

                with col3:
                    if st.button("🛑 Отменить", key=f"cancel_{session_id}", type="secondary"):
                        _cancel_analysis(api, admin_token, session_id)
                        st.rerun()

                st.divider()

    except Exception as e:
        st.error(f"❌ Ошибка при получении списка активных анализов: {str(e)}")


def _cancel_analysis(api: ApiClient, admin_token: str, session_id: str) -> None:
    """Отменить анализ по session_id."""
    try:
        result = api.delete(f"/agent/analyze/{session_id}", admin_token=admin_token)

        if result and result.get("status") == "cancelled":
            st.success(f"✅ {result.get('message', 'Анализ отменён успешно')}")
        else:
            st.warning("⚠️ Не удалось отменить анализ или он уже завершён")

    except Exception as e:
        st.error(f"❌ Ошибка при отмене анализа: {str(e)}")


def _render_system_metrics(api: ApiClient, admin_token: str) -> None:
    """Системные метрики: CPU, память, соединения."""
    st.subheader("💻 Системные метрики")

    metrics = api.get("/admin/metrics/system", admin_token=admin_token)

    if not metrics:
        st.error("❌ Не удалось получить системные метрики")
        return

    # Метрики памяти
    memory = metrics.get("memory", {})
    col1, col2, col3 = st.columns(3)

    with col1:
        rss_mb = memory.get("rss_mb", 0)
        st.metric(
            label="💾 Физическая память (RSS)",
            value=f"{rss_mb:.1f} МБ",
            help="Resident Set Size - физическая память процесса",
        )

    with col2:
        vms_mb = memory.get("vms_mb", 0)
        st.metric(
            label="🗂️ Виртуальная память",
            value=f"{vms_mb:.1f} МБ",
            help="Виртуальная память процесса",
        )

    with col3:
        mem_percent = memory.get("percent", 0)
        st.metric(
            label="📊 Использование памяти",
            value=f"{mem_percent:.1f}%",
            help="Процент использования памяти",
        )

    st.divider()

    # CPU и потоки
    cpu = metrics.get("cpu", {})
    connections_data = metrics.get("connections", {})

    col1, col2, col3 = st.columns(3)

    with col1:
        cpu_percent = cpu.get("percent", 0)
        st.metric(
            label="⚡ Использование CPU",
            value=f"{cpu_percent:.1f}%",
            help="Использование CPU процессом",
        )

    with col2:
        num_threads = cpu.get("num_threads", 0)
        st.metric(label="🧵 Потоки", value=num_threads, help="Количество активных потоков")

    with col3:
        open_connections = connections_data.get("connections", 0)
        st.metric(
            label="🔗 Открытые соединения",
            value=open_connections,
            help="Количество открытых сетевых соединений",
        )

    # Открытые файлы
    open_files = connections_data.get("open_files", 0)
    st.metric(
        label="📁 Открытые файлы",
        value=open_files,
        help="Количество открытых файловых дескрипторов",
    )

    # Предупреждения
    if mem_percent > 80:
        st.warning("⚠️ Высокое использование памяти (>80%)!")

    if cpu_percent > 90:
        st.warning("⚠️ Высокое использование CPU (>90%)!")

    if open_files > 1000:
        st.warning("⚠️ Много открытых файлов (>1000)! Возможна утечка дескрипторов.")

    # Детали в expander
    with st.expander("📋 Исходные данные"):
        st.json(metrics)


def _render_llm_statistics(api: ApiClient, admin_token: str) -> None:
    """Статистика LLM вызовов."""
    st.subheader("🧠 Статистика LLM вызовов")

    # Выбор периода
    hours = st.slider("📅 Период (часы)", min_value=1, max_value=168, value=24, step=1)

    stats = api.get("/admin/llm/stats", params={"hours": hours}, admin_token=admin_token)

    if not stats:
        st.error("❌ Не удалось получить статистику LLM")
        return

    # Общая статистика
    total_calls = stats.get("total_calls", 0)
    successful_calls = stats.get("successful_calls", 0)
    failed_calls = stats.get("failed_calls", 0)
    cache_hits = stats.get("cache_hits", 0)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📞 Всего вызовов",
            value=total_calls,
            help=f"Всего LLM вызовов за {hours}ч",
        )

    with col2:
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
        st.metric(
            label="✅ Успешность",
            value=f"{success_rate:.1f}%",
            delta=f"{successful_calls} вызовов",
            help="Процент успешных вызовов",
        )

    with col3:
        cache_hit_rate = (cache_hits / total_calls * 100) if total_calls > 0 else 0
        st.metric(
            label="💾 Попадания в кэш",
            value=f"{cache_hit_rate:.1f}%",
            delta=f"{cache_hits} попаданий",
            help="Процент попаданий в кэш (экономия времени)",
        )

    with col4:
        st.metric(
            label="❌ Ошибки",
            value=failed_calls,
            delta=f"{(failed_calls / total_calls * 100) if total_calls > 0 else 0:.1f}%",
            delta_color="inverse",
            help="Количество неудачных вызовов",
        )

    # Метрики производительности
    avg_duration = stats.get("avg_duration_ms", 0)
    max_duration = stats.get("max_duration_ms", 0)

    st.divider()
    st.markdown("### ⏱️ Производительность")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="⏱️ Среднее время",
            value=f"{avg_duration:.0f} мс",
            help="Среднее время LLM вызова",
        )

    with col2:
        st.metric(
            label="🐌 Максимальное время",
            value=f"{max_duration:.0f} мс",
            help="Максимальное время LLM вызова",
        )

    # Статистика по провайдерам
    providers_stats = stats.get("by_provider", {})
    if providers_stats:
        st.divider()
        st.markdown("### 🔌 По провайдерам")

        for provider, provider_stats in providers_stats.items():
            with st.expander(f"📊 {provider.upper()}"):
                p_calls = provider_stats.get("calls", 0)
                p_success = provider_stats.get("successful", 0)
                p_avg = provider_stats.get("avg_duration_ms", 0)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Вызовов", p_calls)
                with col2:
                    st.metric("Успешно", p_success)
                with col3:
                    st.metric("Среднее время", f"{p_avg:.0f} мс")

    # Последние вызовы
    st.divider()
    st.markdown("### 📝 Последние вызовы")

    limit = st.slider("Количество записей", min_value=5, max_value=100, value=20, step=5)

    recent = api.get("/admin/llm/recent", params={"limit": limit}, admin_token=admin_token)

    if recent and recent.get("calls"):
        for call in recent["calls"][:10]:  # Показываем max 10 в основном виде
            timestamp = call.get("timestamp", "")
            provider = call.get("provider", "unknown")
            duration = call.get("duration_ms", 0)
            success = call.get("success", False)
            cache_hit = call.get("cache_hit", False)

            status_emoji = "✅" if success else "❌"
            cache_emoji = "💾" if cache_hit else "🔍"

            st.caption(f"{status_emoji} {cache_emoji} [{timestamp}] {provider.upper()} - {duration:.0f} мс")

        with st.expander("📋 Все недавние вызовы"):
            st.json(recent)
    else:
        st.info("📭 Нет недавних LLM вызовов")

    # Предупреждения
    if cache_hit_rate < 20 and total_calls > 10:
        st.warning(
            f"⚠️ Низкий процент попаданий в кэш ({cache_hit_rate:.1f}%). Рассмотрите возможность увеличения TTL кэша."
        )

    if failed_calls / total_calls > 0.1 if total_calls > 0 else False:
        st.error(
            f"❌ Высокий процент ошибок ({failed_calls / total_calls * 100:.1f}%). "
            "Проверьте логи и доступность LLM провайдеров."
        )


def _render_cache_statistics(api: ApiClient, admin_token: str) -> None:
    """Статистика кэша."""
    st.subheader("💾 Статистика кэша")

    stats = api.get("/admin/cache/stats", admin_token=admin_token)

    if not stats:
        st.error("❌ Не удалось получить статистику кэша")
        return

    # Общая статистика
    total_entries = stats.get("total_entries", 0)
    total_hits = stats.get("total_hits", 0)
    total_misses = stats.get("total_misses", 0)
    total_requests = total_hits + total_misses
    hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📦 Всего записей",
            value=total_entries,
            help="Общее количество записей в кэше",
        )

    with col2:
        st.metric(
            label="✅ Попадания",
            value=total_hits,
            help="Количество успешных попаданий",
        )

    with col3:
        st.metric(label="❌ Промахи", value=total_misses, help="Количество промахов")

    with col4:
        st.metric(
            label="📊 Процент попаданий",
            value=f"{hit_rate:.1f}%",
            help="Процент попаданий в кэш",
        )

    # Кэш по источникам
    by_source = stats.get("by_source", {})
    if by_source:
        st.divider()
        st.markdown("### 🗂️ По источникам")

        for source, source_stats in by_source.items():
            with st.expander(f"📂 {source}"):
                s_entries = source_stats.get("entries", 0)
                s_hits = source_stats.get("hits", 0)
                s_misses = source_stats.get("misses", 0)
                s_requests = s_hits + s_misses
                s_hit_rate = (s_hits / s_requests * 100) if s_requests > 0 else 0

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Записей", s_entries)
                with col2:
                    st.metric("Попаданий", s_hits)
                with col3:
                    st.metric("Промахов", s_misses)
                with col4:
                    st.metric("Процент попаданий", f"{s_hit_rate:.1f}%")

    # Управление кэшем
    st.divider()
    st.markdown("### 🗑️ Управление кэшем")

    source_options = {
        "all": "Весь кэш",
        "llm_cache": "LLM кэш",
        "dadata": "DaData",
        "infosphere": "InfoSphere",
        "casebook": "Casebook",
        "perplexity": "Perplexity",
        "tavily": "Tavily",
    }

    source_to_clear = st.selectbox(
        "Выберите источник для очистки",
        options=list(source_options.keys()),
        format_func=lambda x: source_options[x],
        index=0,
    )

    confirm_clear = st.checkbox(f"✅ Подтвердить очистку кэша ({source_options[source_to_clear]})", value=False)

    if st.button("🗑️ Очистить кэш", disabled=not confirm_clear, type="secondary"):
        clear_payload = {"source": source_to_clear if source_to_clear != "all" else None}
        result = api.post("/admin/cache/clear", json=clear_payload, admin_token=admin_token)

        if result:
            st.success(f"✅ Кэш {source_options[source_to_clear]} успешно очищен!")
            st.rerun()
        else:
            st.error("❌ Ошибка при очистке кэша")

    # Предупреждения
    if hit_rate < 30 and total_requests > 100:
        st.warning(f"⚠️ Низкий процент попаданий ({hit_rate:.1f}%). Возможно, стоит увеличить TTL или объём кэша.")

    if total_entries > 10000:
        st.warning(
            f"⚠️ Большое количество записей в кэше ({total_entries}). Рассмотрите возможность очистки старых записей."
        )


def _render_health_status(api: ApiClient, admin_token: str) -> None:
    """Детальный статус здоровья системы."""
    st.subheader("🏥 Статус здоровья системы")

    health = api.get("/admin/health/detailed", admin_token=admin_token)

    if not health:
        st.error("❌ Не удалось получить статус здоровья")
        return

    # Общий статус
    overall_status = health.get("status", "unknown")

    status_messages = {
        "healthy": ("✅ Система работает нормально", "success"),
        "degraded": ("⚠️ Система работает в деградированном режиме", "warning"),
        "unhealthy": ("❌ Система неработоспособна", "error"),
    }

    message, msg_type = status_messages.get(overall_status, ("❓ Статус неизвестен", "info"))
    getattr(st, msg_type)(message)

    timestamp = health.get("timestamp", "")
    st.caption(f"🕐 Проверено: {timestamp}")

    st.divider()

    # Статус компонентов
    components = health.get("components", {})

    component_names = {
        "tarantool": "Tarantool (кэш)",
        "http_client": "HTTP клиент",
        "llm": "LLM провайдеры",
        "memory_monitor": "Мониторинг памяти",
        "rabbitmq": "RabbitMQ",
        "email": "Email (SMTP)",
    }

    status_labels = {
        "healthy": "работает",
        "degraded": "деградация",
        "unhealthy": "недоступен",
        "error": "ошибка",
    }

    for component_name, component_status in components.items():
        status = component_status.get("status", "unknown")
        message = component_status.get("message", "")
        details = component_status.get("details", {})

        # Emoji по статусу
        if status == "healthy":
            emoji = "✅"
            color = "normal"
        elif status == "degraded":
            emoji = "⚠️"
            color = "warning"
        else:
            emoji = "❌"
            color = "error"

        display_name = component_names.get(component_name, component_name.upper())
        status_label = status_labels.get(status, status)

        with st.expander(f"{emoji} {display_name}: {status_label}"):
            if message:
                if color == "normal":
                    st.success(message)
                elif color == "warning":
                    st.warning(message)
                else:
                    st.error(message)

            if details:
                st.json(details)

    # Обнаруженные проблемы
    issues = health.get("issues", [])
    if issues:
        st.divider()
        st.markdown("### ⚠️ Обнаруженные проблемы")
        for issue in issues:
            st.error(f"❌ {issue}")

    # Исходные данные
    with st.expander("📋 Исходные данные"):
        st.json(health)
