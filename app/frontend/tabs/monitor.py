from __future__ import annotations

import time

import streamlit as st

from app.frontend.api_client import ApiClient


def render(api: ApiClient, *, admin_token: str) -> None:
    """
    System Monitor - real-time мониторинг производительности и здоровья системы.

    Использует admin endpoints:
    - GET /admin/cache/stats - Cache statistics
    - GET /admin/llm/stats - LLM call statistics
    - GET /admin/health/detailed - Detailed health check
    - GET /admin/metrics/system - System metrics (CPU, memory)
    """
    st.header("📊 System Monitor")

    st.info("🔒 Real-time мониторинг системы. Обновление по запросу.")

    # Auto-refresh опция
    auto_refresh = st.checkbox("🔄 Auto-refresh каждые 5 секунд", value=False)

    if auto_refresh:
        if "last_refresh" not in st.session_state:
            st.session_state["last_refresh"] = time.time()

        elapsed = time.time() - st.session_state["last_refresh"]
        if elapsed >= 5:
            st.session_state["last_refresh"] = time.time()
            st.rerun()

        st.caption(f"⏱️ Next refresh in {5 - int(elapsed)}s")

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
            "📈 System Metrics",
            "🧠 LLM Statistics",
            "💾 Cache Statistics",
            "🏥 Health Status",
        ]
    )

    with tabs[0]:
        _render_system_metrics(api, admin_token)

    with tabs[1]:
        _render_llm_statistics(api, admin_token)

    with tabs[2]:
        _render_cache_statistics(api, admin_token)

    with tabs[3]:
        _render_health_status(api, admin_token)


def _render_system_metrics(api: ApiClient, admin_token: str) -> None:
    """Системные метрики: CPU, память, connections."""
    st.subheader("💻 System Metrics")

    metrics = api.get("/admin/metrics/system", admin_token=admin_token)

    if not metrics:
        st.error("❌ Не удалось получить системные метрики")
        return

    # Memory metrics
    memory = metrics.get("memory", {})
    col1, col2, col3 = st.columns(3)

    with col1:
        rss_mb = memory.get("rss_mb", 0)
        st.metric(
            label="💾 RSS Memory",
            value=f"{rss_mb:.1f} MB",
            help="Resident Set Size - физическая память процесса",
        )

    with col2:
        vms_mb = memory.get("vms_mb", 0)
        st.metric(
            label="🗂️ Virtual Memory",
            value=f"{vms_mb:.1f} MB",
            help="Виртуальная память процесса",
        )

    with col3:
        mem_percent = memory.get("percent", 0)
        st.metric(
            label="📊 Memory %",
            value=f"{mem_percent:.1f}%",
            help="Процент использования памяти",
        )

    st.divider()

    # CPU & Threads
    cpu = metrics.get("cpu", {})
    connections_data = metrics.get("connections", {})

    col1, col2, col3 = st.columns(3)

    with col1:
        cpu_percent = cpu.get("percent", 0)
        st.metric(
            label="⚡ CPU Usage",
            value=f"{cpu_percent:.1f}%",
            help="Использование CPU процессом",
        )

    with col2:
        num_threads = cpu.get("num_threads", 0)
        st.metric(
            label="🧵 Threads", value=num_threads, help="Количество активных потоков"
        )

    with col3:
        open_connections = connections_data.get("connections", 0)
        st.metric(
            label="🔗 Open Connections",
            value=open_connections,
            help="Количество открытых сетевых соединений",
        )

    # Open files
    open_files = connections_data.get("open_files", 0)
    st.metric(
        label="📁 Open Files",
        value=open_files,
        help="Количество открытых файловых дескрипторов",
    )

    # Warnings
    if mem_percent > 80:
        st.warning("⚠️ Высокое использование памяти (>80%)!")

    if cpu_percent > 90:
        st.warning("⚠️ Высокое использование CPU (>90%)!")

    if open_files > 1000:
        st.warning("⚠️ Много открытых файлов (>1000)! Возможна утечка дескрипторов.")

    # Детали в expander
    with st.expander("📋 Raw Metrics"):
        st.json(metrics)


def _render_llm_statistics(api: ApiClient, admin_token: str) -> None:
    """Статистика LLM вызовов."""
    st.subheader("🧠 LLM Call Statistics")

    # Выбор периода
    hours = st.slider("📅 Период (часы)", min_value=1, max_value=168, value=24, step=1)

    stats = api.get(
        "/admin/llm/stats", params={"hours": hours}, admin_token=admin_token
    )

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
            label="📞 Total Calls",
            value=total_calls,
            help=f"Всего LLM вызовов за {hours}ч",
        )

    with col2:
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
        st.metric(
            label="✅ Success Rate",
            value=f"{success_rate:.1f}%",
            delta=f"{successful_calls} calls",
            help="Процент успешных вызовов",
        )

    with col3:
        cache_hit_rate = (cache_hits / total_calls * 100) if total_calls > 0 else 0
        st.metric(
            label="💾 Cache Hit Rate",
            value=f"{cache_hit_rate:.1f}%",
            delta=f"{cache_hits} hits",
            help="Процент попаданий в кэш (экономия времени)",
        )

    with col4:
        st.metric(
            label="❌ Failed Calls",
            value=failed_calls,
            delta=f"{(failed_calls / total_calls * 100) if total_calls > 0 else 0:.1f}%",
            delta_color="inverse",
            help="Количество неудачных вызовов",
        )

    # Timing metrics
    avg_duration = stats.get("avg_duration_ms", 0)
    max_duration = stats.get("max_duration_ms", 0)

    st.divider()
    st.markdown("### ⏱️ Performance Metrics")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="⏱️ Avg Duration",
            value=f"{avg_duration:.0f} ms",
            help="Среднее время LLM вызова",
        )

    with col2:
        st.metric(
            label="🐌 Max Duration",
            value=f"{max_duration:.0f} ms",
            help="Максимальное время LLM вызова",
        )

    # Provider breakdown
    providers_stats = stats.get("by_provider", {})
    if providers_stats:
        st.divider()
        st.markdown("### 🔌 By Provider")

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
                    st.metric("Средняя длительность", f"{p_avg:.0f} ms")

    # Recent calls
    st.divider()
    st.markdown("### 📝 Последние вызовы")

    limit = st.slider(
        "Количество записей", min_value=5, max_value=100, value=20, step=5
    )

    recent = api.get(
        "/admin/llm/recent", params={"limit": limit}, admin_token=admin_token
    )

    if recent and recent.get("calls"):
        for call in recent["calls"][:10]:  # Show max 10 in main view
            timestamp = call.get("timestamp", "")
            provider = call.get("provider", "unknown")
            duration = call.get("duration_ms", 0)
            success = call.get("success", False)
            cache_hit = call.get("cache_hit", False)

            status_emoji = "✅" if success else "❌"
            cache_emoji = "💾" if cache_hit else "🔍"

            st.caption(
                f"{status_emoji} {cache_emoji} [{timestamp}] {provider.upper()} - {duration:.0f}ms"
            )

        with st.expander("📋 All Recent Calls"):
            st.json(recent)
    else:
        st.info("📭 Нет недавних LLM вызовов")

    # Warnings
    if cache_hit_rate < 20 and total_calls > 10:
        st.warning(
            f"⚠️ Низкий cache hit rate ({cache_hit_rate:.1f}%). "
            "Рассмотрите возможность увеличения TTL кэша."
        )

    if failed_calls / total_calls > 0.1 if total_calls > 0 else False:
        st.error(
            f"❌ Высокий процент ошибок ({failed_calls / total_calls * 100:.1f}%). "
            "Проверьте логи и доступность LLM провайдеров."
        )


def _render_cache_statistics(api: ApiClient, admin_token: str) -> None:
    """Статистика кэша."""
    st.subheader("💾 Cache Statistics")

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
            label="📦 Total Entries",
            value=total_entries,
            help="Общее количество записей в кэше",
        )

    with col2:
        st.metric(
            label="✅ Cache Hits",
            value=total_hits,
            help="Количество успешных попаданий",
        )

    with col3:
        st.metric(
            label="❌ Cache Misses", value=total_misses, help="Количество промахов"
        )

    with col4:
        st.metric(
            label="📊 Hit Rate",
            value=f"{hit_rate:.1f}%",
            help="Процент попаданий в кэш",
        )

    # Cache by source
    by_source = stats.get("by_source", {})
    if by_source:
        st.divider()
        st.markdown("### 🗂️ By Source")

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

    # Cache management
    st.divider()
    st.markdown("### 🗑️ Управление кэшем")

    source_to_clear = st.selectbox(
        "Выберите source для очистки",
        options=[
            "all",
            "llm_cache",
            "dadata",
            "infosphere",
            "casebook",
            "perplexity",
            "tavily",
        ],
        index=0,
    )

    confirm_clear = st.checkbox(
        f"✅ Подтвердить очистку кэша ({source_to_clear})", value=False
    )

    if st.button("🗑️ Очистить кэш", disabled=not confirm_clear, type="secondary"):
        clear_payload = {
            "source": source_to_clear if source_to_clear != "all" else None
        }
        result = api.post(
            "/admin/cache/clear", json=clear_payload, admin_token=admin_token
        )

        if result:
            st.success(f"✅ Кэш {source_to_clear} успешно очищен!")
            st.rerun()
        else:
            st.error("❌ Ошибка при очистке кэша")

    # Warnings
    if hit_rate < 30 and total_requests > 100:
        st.warning(
            f"⚠️ Низкий cache hit rate ({hit_rate:.1f}%). "
            "Возможно, стоит увеличить TTL или объем кэша."
        )

    if total_entries > 10000:
        st.warning(
            f"⚠️ Большое количество записей в кэше ({total_entries}). "
            "Рассмотрите возможность очистки старых записей."
        )


def _render_health_status(api: ApiClient, admin_token: str) -> None:
    """Детальный статус здоровья системы."""
    st.subheader("🏥 System Health Status")

    health = api.get("/admin/health/detailed", admin_token=admin_token)

    if not health:
        st.error("❌ Не удалось получить статус здоровья")
        return

    # Общий статус
    overall_status = health.get("status", "unknown")

    if overall_status == "healthy":
        st.success("✅ Система работает нормально")
    elif overall_status == "degraded":
        st.warning("⚠️ Система работает в деградированном режиме")
    else:
        st.error("❌ Система неработоспособна")

    timestamp = health.get("timestamp", "")
    st.caption(f"🕐 Проверено: {timestamp}")

    st.divider()

    # Components status
    components = health.get("components", {})

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

        with st.expander(f"{emoji} {component_name.upper()}: {status}"):
            if message:
                if color == "normal":
                    st.success(message)
                elif color == "warning":
                    st.warning(message)
                else:
                    st.error(message)

            if details:
                st.json(details)

    # Issues summary
    issues = health.get("issues", [])
    if issues:
        st.divider()
        st.markdown("### ⚠️ Detected Issues")
        for issue in issues:
            st.error(f"❌ {issue}")

    # Raw data
    with st.expander("📋 Raw Health Data"):
        st.json(health)
