import os

import requests
import streamlit as st

# ========================
# Настройка страницы
# ========================
st.set_page_config(page_title="Multi-Agent System", layout="wide")
st.title("Multi-Agent System Console")

# ========================
# Константы
# ========================
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
API_BASE_URL = f"http://localhost:{BACKEND_PORT}"

# ========================
# Инициализация состояния
# ========================
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "last_thread_id" not in st.session_state:
    st.session_state.last_thread_id = None
if "threads" not in st.session_state:
    st.session_state.threads = []
if "page" not in st.session_state:
    st.session_state.page = "Запрос агенту"

# ========================
# Боковая панель навигации
# ========================
PAGES = ["Запрос агенту", "История", "Внешние данные", "Утилиты"]
st.sidebar.title("Навигация")
page = st.sidebar.radio(
    "Выберите раздел",
    PAGES,
    index=PAGES.index(st.session_state.page) if st.session_state.page in PAGES else 0,
    key="nav_radio",
)
st.session_state.page = page

# ========================
# Страница: Запрос агенту
# ========================
if page == "Запрос агенту":
    st.header("📝 Отправить запрос агенту")

    with st.form("agent_query_form"):
        query = st.text_area(
            "Введите ваш запрос:",
            height=150,
            placeholder="Например: Проанализируй компанию с ИНН 7707083893",
        )
        submitted = st.form_submit_button("🚀 Отправить запрос")

    if submitted and query.strip():
        with st.spinner("Агенты работают..."):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/agent/prompt",
                    json={"prompt": query.strip()},
                    timeout=60,
                )
                if response.status_code == 200:
                    result = response.json()
                    st.session_state.last_response = result
                    st.session_state.last_thread_id = result.get("thread_id")
                    st.rerun()
                else:
                    st.error(
                        f"Ошибка сервера: {response.status_code} - {response.text}"
                    )
            except requests.exceptions.Timeout:
                st.error("⏳ Таймаут: запрос занимает слишком много времени.")
            except Exception as e:
                st.error(f"❌ Ошибка подключения: {e}")

    # Отображение результата
    if st.session_state.last_response:
        result = st.session_state.last_response
        st.success("✅ Запрос выполнен!")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 📊 Результат:")
            st.markdown(result.get("response", "Нет ответа"))
        with col2:
            st.markdown("### 🧩 Метаданные:")
            st.write(f"**Thread ID:** `{result.get('thread_id', 'N/A')}`")
            st.write(f"**Инструменты:** {'Да' if result.get('tools_used') else 'Нет'}")
            st.write(f"**Время:** {result.get('timestamp', 'N/A')}")

        # Кнопка копирования
        st.code(result.get("response", ""), language="text")
        st.download_button(
            "💾 Скачать ответ",
            data=result.get("response", ""),
            file_name=f"response_{result.get('thread_id', 'unknown')}.txt",
            mime="text/plain",
        )

        # Кнопка перехода к истории
        if st.button("📋 Просмотреть в истории"):
            st.session_state.selected_thread_id = result.get("thread_id")
            st.session_state.page = "История"
            st.rerun()

        st.divider()

# ========================
# Страница: История
# ========================
elif page == "История":
    st.header("📚 История запросов")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🔄 Обновить список", type="primary"):
            try:
                with st.spinner("Загрузка..."):
                    resp = requests.get(f"{API_BASE_URL}/agent/threads", timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state.threads = data.get("threads", [])
                        st.success(f"Загружено {len(st.session_state.threads)} записей")
                    else:
                        st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка загрузки: {e}")

    # Отображение списка
    if st.session_state.threads:
        for thread in st.session_state.threads:
            with st.expander(f"📌 {thread['user_prompt']}"):
                st.write(f"**ID:** `{thread['thread_id']}`")
                st.write(f"**Создано:** {thread['created_at']}")
                st.write(f"**Сообщений:** {thread['message_count']}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("👁️ Просмотреть", key=f"view_{thread['thread_id']}"):
                        try:
                            resp = requests.get(
                                f"{API_BASE_URL}/agent/thread_history/{thread['thread_id']}",
                                timeout=10,
                            )
                            if resp.status_code == 200:
                                st.json(resp.json())
                            else:
                                st.error("Запись не найдена")
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
                with col2:
                    if st.button("🗑️ Удалить", key=f"del_{thread['thread_id']}"):
                        st.warning("Удаление пока не реализовано")
    else:
        st.info("История пуста. Отправьте первый запрос!")

# ========================
# Страница: Внешние данные
# ========================
elif page == "Внешние данные":
    st.header("🌍 Запросы к внешним источникам")

    with st.form("external_data_form"):
        inn = st.text_input("ИНН", value="7707083893", max_chars=12)
        source = st.selectbox(
            "Источник",
            [
                ("info", "Все источники"),
                ("dadata", "DaData"),
                ("casebook", "Casebook"),
                ("infosphere", "InfoSphere"),
            ],
            format_func=lambda x: x[1],
        )
        submitted = st.form_submit_button("🔍 Получить данные")

    if submitted and inn.strip():
        with st.spinner("Запрос к внешним API..."):
            try:
                url = f"{API_BASE_URL}/data/client/{source[0]}/{inn.strip()}"
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    st.success("✅ Данные получены")
                    st.json(resp.json())
                else:
                    st.error(f"Ошибка: {resp.status_code} - {resp.text}")
            except requests.exceptions.Timeout:
                st.error("⏳ Таймаут: внешний сервис не ответил.")
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

# ========================
# Страница: Утилиты (Service Dashboard)
# ========================
elif page == "Утилиты":
    st.header("📊 Service Dashboard")

    if "service_statuses" not in st.session_state:
        st.session_state.service_statuses = {}

    def check_service_status(service_name, endpoint, timeout=10):
        try:
            resp = requests.get(f"{API_BASE_URL}{endpoint}", timeout=timeout)
            if resp.status_code == 200:
                return {"status": "ok", "data": resp.json(), "latency": resp.elapsed.total_seconds()}
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    st.subheader("🔌 Service Status Cards")

    if st.button("🔄 Check All Services", type="primary"):
        with st.spinner("Checking services..."):
            st.session_state.service_statuses = {
                "openrouter": check_service_status("OpenRouter LLM", "/utility/openrouter/status"),
                "perplexity": check_service_status("Perplexity", "/utility/perplexity/status"),
                "tavily": check_service_status("Tavily", "/utility/tavily/status"),
                "tarantool": check_service_status("Tarantool/Redis", "/utility/tarantool/status"),
                "health": check_service_status("Health", "/utility/health"),
            }

    col1, col2, col3, col4 = st.columns(4)

    def render_status_card(col, name, icon, key):
        with col:
            status = st.session_state.service_statuses.get(key, {})
            if not status:
                st.markdown(f"### {icon} {name}")
                st.info("Click 'Check All Services'")
            elif status.get("status") == "ok":
                st.markdown(f"### {icon} {name}")
                st.success(f"OK ({status.get('latency', 0):.2f}s)")
                data = status.get("data", {})
                if key == "openrouter":
                    st.caption(f"Model: {data.get('model', 'N/A')}")
                    st.caption(f"Available: {'Yes' if data.get('available') else 'No'}")
                elif key == "perplexity":
                    st.caption(f"Configured: {'Yes' if data.get('configured') else 'No'}")
                elif key == "tavily":
                    st.caption(f"Configured: {'Yes' if data.get('configured') else 'No'}")
                elif key == "tarantool":
                    st.caption(f"Mode: {data.get('mode', 'N/A')}")
                    cache = data.get("cache", {})
                    st.caption(f"Cache size: {cache.get('size', 0)}")
            else:
                st.markdown(f"### {icon} {name}")
                st.error(f"Error: {status.get('error', 'Unknown')}")

    render_status_card(col1, "LLM (OpenRouter)", "🤖", "openrouter")
    render_status_card(col2, "Perplexity", "🔍", "perplexity")
    render_status_card(col3, "Tavily", "🌐", "tavily")
    render_status_card(col4, "Cache", "🗄️", "tarantool")

    st.divider()

    st.subheader("🔍 Search Tools Test")

    search_tab1, search_tab2 = st.tabs(["Perplexity Search", "Tavily Search"])

    with search_tab1:
        with st.form("perplexity_search_form"):
            perp_query = st.text_input("Search query:", placeholder="e.g., Latest news about AI")
            perp_submit = st.form_submit_button("Search via Perplexity")

        if perp_submit and perp_query.strip():
            with st.spinner("Searching with Perplexity..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/perplexity/search",
                        json={"query": perp_query.strip()},
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            st.success("Search completed!")
                            st.markdown("**Response:**")
                            st.markdown(result.get("content", "No content"))
                            if result.get("citations"):
                                with st.expander("Citations"):
                                    for cite in result.get("citations", []):
                                        st.write(f"- {cite}")
                        else:
                            st.error(result.get("message", "Unknown error"))
                    else:
                        st.error(f"API Error: {resp.status_code}")
                except Exception as e:
                    st.error(f"Error: {e}")

    with search_tab2:
        with st.form("tavily_search_form"):
            tav_query = st.text_input("Search query:", placeholder="e.g., Python best practices 2024")
            tav_depth = st.selectbox("Search depth:", ["basic", "advanced"])
            tav_max = st.slider("Max results:", 1, 10, 5)
            tav_submit = st.form_submit_button("Search via Tavily")

        if tav_submit and tav_query.strip():
            with st.spinner("Searching with Tavily..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/tavily/search",
                        json={
                            "query": tav_query.strip(),
                            "search_depth": tav_depth,
                            "max_results": tav_max,
                            "include_answer": True,
                        },
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            st.success("Search completed!")
                            if result.get("answer"):
                                st.markdown("**Answer:**")
                                st.markdown(result.get("answer"))
                            st.markdown("**Results:**")
                            for item in result.get("results", []):
                                with st.expander(item.get("title", "No title")):
                                    st.write(item.get("content", ""))
                                    st.caption(item.get("url", ""))
                        else:
                            st.error(result.get("message", "Unknown error"))
                    else:
                        st.error(f"API Error: {resp.status_code}")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()

    st.subheader("🧹 Cache Management")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Clear Perplexity Cache"):
            try:
                resp = requests.post(f"{API_BASE_URL}/utility/perplexity/cache/clear", timeout=10)
                if resp.status_code == 200:
                    st.success("Perplexity cache cleared!")
                else:
                    st.error(f"Error: {resp.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

    with col2:
        if st.button("Clear Tavily Cache"):
            try:
                resp = requests.post(f"{API_BASE_URL}/utility/tavily/cache/clear", timeout=10)
                if resp.status_code == 200:
                    st.success("Tavily cache cleared!")
                else:
                    st.error(f"Error: {resp.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

    with col3:
        confirm = st.checkbox("Confirm full cache clear")
        if st.button("Clear All Cache", disabled=not confirm):
            try:
                resp = requests.get(f"{API_BASE_URL}/utility/validate_cache?confirm=true", timeout=10)
                if resp.status_code == 200:
                    st.success("All cache cleared!")
                else:
                    st.error(f"Error: {resp.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    st.subheader("📈 System Health")

    health_status = st.session_state.service_statuses.get("health", {})  # type: ignore
    if health_status.get("status") == "ok":
        data = health_status.get("data", {})
        overall = data.get("status", "unknown")

        if overall == "healthy":
            st.success(f"System Status: {overall.upper()}")
        elif overall == "degraded":
            st.warning(f"System Status: {overall.upper()}")
            issues = data.get("issues", [])
            if issues:
                st.markdown("**Issues:**")
                for issue in issues:
                    st.write(f"- {issue}")
        else:
            st.error(f"System Status: {overall.upper()}")

        components = data.get("components", {})
        if components:
            with st.expander("Component Details"):
                st.json(components)
    else:
        st.info("Click 'Check All Services' to see system health")
