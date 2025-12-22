"""
Страница утилит администратора.

Доступна только для администраторов.
Содержит мониторинг, управление кэшем, логи, метрики.
"""

import streamlit as st

# Для pages/ НЕ нужен set_page_config - Streamlit сам управляет

import os
import sys

# Add lib to path - ABSOLUTE path to avoid issues
current_file = os.path.abspath(__file__)
pages_dir = os.path.dirname(current_file)
frontend_dir = os.path.dirname(pages_dir)
lib_dir = os.path.join(frontend_dir, "lib")

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from api_client import get_api_client
from components import render_admin_settings, render_empty_state, render_sidebar_auth

# Sidebar (without title - Streamlit adds navigation automatically)
with st.sidebar:
    render_sidebar_auth()
    render_admin_settings()

# ==============================================================================
# ACCESS CONTROL
# ==============================================================================

if not st.session_state.get("is_admin", False):
    st.warning("🔒 Доступ только для администратора")
    st.info("Войдите с токеном администратора в боковой панели")
    st.stop()

# ==============================================================================
# MAIN CONTENT
# ==============================================================================

st.title("⚙️ Административные утилиты")

st.markdown("""
Управление системой, мониторинг сервисов, просмотр логов и метрик.
""")

st.divider()

client = get_api_client()

# ==============================================================================
# SERVICE STATUS
# ==============================================================================

st.subheader("🔧 Статус сервисов")

if st.button("🔄 Обновить статусы", type="primary"):
    st.session_state.force_refresh_services = True

try:
    with st.spinner("Проверка сервисов..."):
        # OpenRouter
        openrouter_status = client.get("/utility/openrouter/status")
        
        # Perplexity
        perplexity_status = client.get("/utility/perplexity/status")
        
        # Tavily
        tavily_status = client.get("/utility/tavily/status")
        
        # Tarantool
        tarantool_status = client.get("/utility/tarantool/status")
        
        # Email
        email_status = client.get("/utility/email/status")
    
    # Display services
    col1, col2, col3 = st.columns(3)
    
    services = [
        (col1, "🤖 OpenRouter LLM", openrouter_status),
        (col2, "🔍 Perplexity AI", perplexity_status),
        (col3, "🌐 Tavily Search", tavily_status),
    ]
    
    for col, name, status in services:
        with col:
            st.markdown(f"**{name}**")
            
            if status.get("available") or status.get("status") == "success":
                st.success("✅ Доступен")
                
                if "model" in status:
                    st.caption(f"Модель: {status['model']}")
            else:
                st.error("❌ Недоступен")
                
                if "error" in status:
                    with st.expander("Ошибка"):
                        st.caption(status["error"])
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    infra = [
        (col1, "💾 Tarantool Cache", tarantool_status),
        (col2, "📧 Email (SMTP)", email_status),
    ]
    
    for col, name, status in infra:
        with col:
            st.markdown(f"**{name}**")
            
            if status.get("available"):
                st.success("✅ Работает")
                
                if "mode" in status:
                    st.caption(f"Режим: {status['mode']}")
                
                if "cache" in status:
                    cache = status["cache"]
                    st.caption(f"Записей: {cache.get('size', 0)}")
                    st.caption(f"Hit rate: {cache.get('hit_rate', 0):.1f}%")
            else:
                st.warning("⚠️ Недоступен")

except Exception as e:
    st.error(f"❌ Ошибка проверки сервисов: {e}")

st.divider()

# ==============================================================================
# CACHE MANAGEMENT
# ==============================================================================

st.subheader("💾 Управление кэшем")

with st.container():
    # Cache metrics
    try:
        cache_metrics = client.get("/utility/cache/metrics")
        
        if cache_metrics.get("status") == "success":
            metrics = cache_metrics.get("metrics", {})
            cache_size = cache_metrics.get("cache_size", 0)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Записей в кэше", cache_size)
            
            with col2:
                hit_rate = metrics.get("hit_rate", 0)
                st.metric("Hit Rate", f"{hit_rate:.1f}%")
            
            with col3:
                hits = metrics.get("hits", 0)
                misses = metrics.get("misses", 0)
                st.metric("Hits/Misses", f"{hits}/{misses}")
    
    except Exception as e:
        st.error(f"Ошибка метрик кэша: {e}")
    
    st.divider()
    
    # Cache actions
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ Очистить кэш поиска", use_container_width=True):
            try:
                result = client.delete("/utility/cache/prefix/search:")
                if result.get("status") == "success":
                    st.success("✅ Кэш поиска очищен")
                else:
                    st.error("❌ Ошибка очистки")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    
    with col2:
        if st.button("🗑️ Tavily кэш", use_container_width=True):
            try:
                result = client.post("/utility/tavily/cache/clear", json={})
                if result.get("status") == "success":
                    st.success("✅ Tavily кэш очищен")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    
    with col3:
        if st.button("🗑️ Perplexity кэш", use_container_width=True):
            try:
                result = client.post("/utility/perplexity/cache/clear", json={})
                if result.get("status") == "success":
                    st.success("✅ Perplexity кэш очищен")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    
    st.divider()
    
    # Full cache clear
    confirm_full = st.checkbox("⚠️ Подтверждаю полную очистку кэша")
    
    if st.button("🗑️ Очистить весь кэш", disabled=not confirm_full, type="secondary"):
        try:
            result = client.get("/utility/validate_cache", params={"confirm": "true"})
            if result.get("status") == "success":
                st.success("✅ Весь кэш очищен")
        except Exception as e:
            st.error(f"Ошибка: {e}")

st.divider()

# ==============================================================================
# METRICS
# ==============================================================================

st.subheader("📊 Метрики HTTP клиентов")

col1, col2 = st.columns(2)

with col1:
    if st.button("📊 Обновить метрики", use_container_width=True):
        st.session_state.force_refresh_metrics = True

with col2:
    if st.button("🔄 Сбросить метрики", use_container_width=True):
        try:
            result = client.post("/utility/metrics/reset", json={})
            if result.get("status") == "success":
                st.success("✅ Метрики сброшены")
        except Exception as e:
            st.error(f"Ошибка: {e}")

try:
    metrics_data = client.get("/utility/metrics")
    
    if metrics_data.get("status") == "success":
        metrics = metrics_data.get("metrics", {})
        
        # Calculate totals
        total_requests = sum(m.get("total_requests", 0) for m in metrics.values() if isinstance(m, dict))
        total_errors = sum(m.get("errors", 0) for m in metrics.values() if isinstance(m, dict))
        error_rate = (total_errors / total_requests * 100) if total_requests else 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Всего запросов", total_requests)
        
        with col2:
            st.metric("Ошибок", total_errors)
        
        with col3:
            st.metric("Ошибок %", f"{error_rate:.1f}%")
        
        # Details
        if metrics:
            with st.expander("📋 Детализация по сервисам"):
                st.json(metrics)

except Exception as e:
    st.error(f"Ошибка загрузки метрик: {e}")

st.divider()

# ==============================================================================
# LOGS
# ==============================================================================

st.subheader("📝 Логи приложения")

col1, col2, col3, col4 = st.columns(4)

with col1:
    since_minutes = st.selectbox(
        "Период",
        options=[5, 15, 30, 60, 120, 0],
        format_func=lambda x: f"Последние {x} мин" if x else "Все логи",
        index=1,
    )

with col2:
    level_filter = st.selectbox(
        "Уровень",
        options=["", "DEBUG", "INFO", "WARNING", "ERROR"],
        format_func=lambda x: x if x else "Все уровни",
    )

with col3:
    limit = st.number_input("Лимит", min_value=10, max_value=500, value=100)

with col4:
    if st.button("🔄 Обновить логи", type="primary"):
        st.session_state.force_refresh_logs = True

# Load logs
params = {"limit": limit}
if since_minutes:
    params["since_minutes"] = since_minutes
if level_filter:
    params["level"] = level_filter

try:
    logs_data = client.get("/utility/logs", params=params)
    
    if logs_data.get("status") == "success":
        logs = logs_data.get("logs", [])
        stats = logs_data.get("stats", {})
        
        # Stats
        if stats:
            with st.container():
                cols = st.columns(5)
                levels = ["total", "DEBUG", "INFO", "WARNING", "ERROR"]
                icons = {"total": "📊", "DEBUG": "🔍", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌"}
                
                for idx, level in enumerate(levels):
                    with cols[idx]:
                        st.metric(f"{icons.get(level, '')} {level}", stats.get(level, 0))
        
        st.divider()
        
        # Logs list
        st.caption(f"Показано: {len(logs)} записей")
        
        if logs:
            for log in logs:
                level = log.get("level", "INFO")
                timestamp = log.get("timestamp", "")[:19]
                message = log.get("message", "")
                logger_name = log.get("logger", "")
                
                # Color by level
                if level == "ERROR":
                    color_icon = "🔴"
                elif level == "WARNING":
                    color_icon = "🟡"
                elif level == "DEBUG":
                    color_icon = "⚪"
                else:
                    color_icon = "🟢"
                
                with st.container():
                    col1, col2 = st.columns([1, 5])
                    
                    with col1:
                        st.caption(f"{color_icon} **{level}**")
                        st.caption(timestamp)
                    
                    with col2:
                        st.text(message[:200] + ("..." if len(message) > 200 else ""))
                        if logger_name:
                            st.caption(f"Logger: {logger_name}")
        else:
            render_empty_state(
                icon="📝",
                title="Нет логов",
                description="За выбранный период логи отсутствуют"
            )
        
        st.divider()
        
        if st.button("🗑️ Очистить все логи", type="secondary"):
            try:
                result = client.post("/utility/logs/clear", json={})
                if result.get("status") == "success":
                    st.success("✅ Логи очищены")
                    st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

except Exception as e:
    st.error(f"Ошибка загрузки логов: {e}")

st.divider()

# ==============================================================================
# SCHEDULER
# ==============================================================================

st.subheader("⏰ Отложенные задачи (Scheduler)")

try:
    # Stats
    stats = client.get("/scheduler/stats")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        running = stats.get("scheduler_running", False)
        st.metric("Статус", "🟢 Активен" if running else "🔴 Остановлен")
    
    with col2:
        scheduled = stats.get("total_scheduled_tasks", 0)
        st.metric("Запланировано", scheduled)
    
    with col3:
        history = stats.get("total_tasks_history", 0)
        st.metric("История задач", history)
    
    # Tasks by status
    if stats.get("tasks_by_status"):
        with st.expander("📊 По статусам"):
            st.json(stats["tasks_by_status"])
    
    st.divider()
    
    # List tasks
    if st.button("🔄 Обновить список задач"):
        st.session_state.force_refresh_tasks = True
    
    tasks_list = client.get("/scheduler/tasks")
    
    if tasks_list:
        st.caption(f"Найдено задач: {len(tasks_list)}")
        
        for task in tasks_list:
            task_id = task.get("task_id", "")
            func_name = task.get("func_name", "")
            status_val = task.get("status", "")
            run_date = task.get("run_date", "")
            metadata = task.get("metadata", {})
            
            with st.expander(f"**{task_id}** — {func_name} — {status_val}"):
                st.write(f"**Запуск:** {run_date}")
                
                if metadata:
                    st.json(metadata)
                
                if st.button("🗑️ Отменить задачу", key=f"cancel_{task_id}"):
                    try:
                        result = client.delete(f"/scheduler/task/{task_id}")
                        if result.get("status") == "success":
                            st.success("✅ Задача отменена")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
    
    else:
        render_empty_state(
            icon="⏰",
            title="Нет активных задач",
            description="Все задачи выполнены или отменены"
        )

except Exception as e:
    st.error(f"Ошибка загрузки задач: {e}")

st.divider()

# ==============================================================================
# CIRCUIT BREAKERS
# ==============================================================================

st.subheader("⚡ Circuit Breakers")

try:
    cb_data = client.get("/utility/circuit-breakers")
    
    if cb_data.get("status") == "success":
        breakers = cb_data.get("circuit_breakers", {})
        
        if breakers:
            for service, cb_info in breakers.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    state = cb_info.get("state", "unknown")
                    icon = "🟢" if state == "closed" else "🔴" if state == "open" else "🟡"
                    st.write(f"{icon} **{service}**: {state}")
                
                with col2:
                    failures = cb_info.get("failures", 0)
                    st.caption(f"Ошибок: {failures}")
                
                with col3:
                    if st.button("🔄 Сброс", key=f"reset_cb_{service}"):
                        try:
                            result = client.post(f"/utility/circuit-breakers/{service}/reset", json={})
                            if result.get("status") == "success":
                                st.success(f"✅ {service} сброшен")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
        else:
            st.info("Нет активных circuit breakers")

except Exception as e:
    st.error(f"Ошибка загрузки circuit breakers: {e}")

st.divider()

# ==============================================================================
# SYSTEM LINKS
# ==============================================================================

st.subheader("🔗 Системные ссылки")

col1, col2 = st.columns(2)

with col1:
    st.link_button("📖 Swagger UI", f"{st.session_state.get('api_base_url', 'http://localhost:8000/api/v1')}/docs")
    st.link_button("📄 OpenAPI JSON", f"{st.session_state.get('api_base_url', 'http://localhost:8000/api/v1')}/openapi.json")

with col2:
    st.link_button("📡 AsyncAPI HTML", f"{st.session_state.get('api_base_url', 'http://localhost:8000/api/v1')}/utility/asyncapi")
    st.link_button("📄 AsyncAPI JSON", f"{st.session_state.get('api_base_url', 'http://localhost:8000/api/v1')}/utility/asyncapi.json")

st.divider()

# ==============================================================================
# HELP
# ==============================================================================

with st.expander("ℹ️ Справка по утилитам"):
    st.markdown("""
    ### Административные функции:
    
    **Статус сервисов:**
    - Проверка доступности внешних API
    - Мониторинг LLM, поисковых сервисов, кэша, email
    
    **Управление кэшем:**
    - Просмотр метрик (hit rate, размер)
    - Очистка кэша по префиксу (поиск, Tavily, Perplexity)
    - Полная очистка кэша (с подтверждением)
    
    **Метрики HTTP:**
    - Общее количество запросов
    - Количество ошибок
    - Процент ошибок
    - Детализация по сервисам
    
    **Логи:**
    - Просмотр логов приложения
    - Фильтрация по уровню (DEBUG, INFO, WARNING, ERROR)
    - Фильтрация по времени
    - Очистка логов
    
    **Scheduler:**
    - Просмотр запланированных задач
    - Отмена задач
    - Статистика выполнения
    
    **Circuit Breakers:**
    - Статус защиты от cascading failures
    - Сброс breakers при необходимости
    
    ---
    
    **⚠️ Внимание:**
    
    Все операции необратимы! Будьте осторожны при:
    - Очистке кэша (данные придётся запросить заново)
    - Очистке логов (потеряете историю)
    - Сбросе метрик (статистика обнулится)
    """)
