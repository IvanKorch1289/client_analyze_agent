import os

import requests
import streamlit as st

st.set_page_config(page_title="Мультиагентная система", layout="wide")
st.title("Мультиагентная система")

BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
API_BASE_URL = f"http://localhost:{BACKEND_PORT}"

if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "last_thread_id" not in st.session_state:
    st.session_state.last_thread_id = None
if "threads" not in st.session_state:
    st.session_state.threads = []
if "page" not in st.session_state:
    st.session_state.page = "Запрос агенту"

PAGES = ["Запрос агенту", "История", "Внешние данные", "Внешние запросы", "Утилиты"]
st.sidebar.title("Навигация")
page = st.sidebar.radio(
    "Выберите раздел",
    PAGES,
    index=PAGES.index(st.session_state.page) if st.session_state.page in PAGES else 0,
    key="nav_radio",
)
st.session_state.page = page

if page == "Запрос агенту":
    st.header("Отправить запрос агенту")

    with st.form("agent_query_form"):
        query = st.text_area(
            "Введите ваш запрос:",
            height=150,
            placeholder="Например: Проанализируй компанию с ИНН 7707083893",
        )
        submitted = st.form_submit_button("Отправить запрос")

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
                st.error("Таймаут: запрос занимает слишком много времени.")
            except Exception as e:
                st.error(f"Ошибка подключения: {e}")

    if st.session_state.last_response:
        result = st.session_state.last_response
        st.success("Запрос выполнен!")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### Результат:")
            st.markdown(result.get("response", "Нет ответа"))
        with col2:
            st.markdown("### Метаданные:")
            st.write(f"**Thread ID:** `{result.get('thread_id', 'Н/Д')}`")
            st.write(f"**Инструменты:** {'Да' if result.get('tools_used') else 'Нет'}")
            st.write(f"**Время:** {result.get('timestamp', 'Н/Д')}")

        st.code(result.get("response", ""), language="text")
        st.download_button(
            "Скачать ответ",
            data=result.get("response", ""),
            file_name=f"response_{result.get('thread_id', 'unknown')}.txt",
            mime="text/plain",
        )

        if st.button("Просмотреть в истории"):
            st.session_state.selected_thread_id = result.get("thread_id")
            st.session_state.page = "История"
            st.rerun()

        st.divider()

elif page == "История":
    st.header("История запросов")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("Обновить список", type="primary"):
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

    if st.session_state.threads:
        for thread in st.session_state.threads:
            with st.expander(f"{thread['user_prompt']}"):
                st.write(f"**ID:** `{thread['thread_id']}`")
                st.write(f"**Создано:** {thread['created_at']}")
                st.write(f"**Сообщений:** {thread['message_count']}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Просмотреть", key=f"view_{thread['thread_id']}"):
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
                    if st.button("Удалить", key=f"del_{thread['thread_id']}"):
                        st.warning("Удаление пока не реализовано")
    else:
        st.info("История пуста. Отправьте первый запрос!")

elif page == "Внешние данные":
    st.header("Запросы к внешним источникам (по ИНН)")

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
        submitted = st.form_submit_button("Получить данные")

    if submitted and inn.strip():
        with st.spinner("Запрос к внешним API..."):
            try:
                url = f"{API_BASE_URL}/data/client/{source[0]}/{inn.strip()}"
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    st.success("Данные получены")
                    st.json(resp.json())
                else:
                    st.error(f"Ошибка: {resp.status_code} - {resp.text}")
            except requests.exceptions.Timeout:
                st.error("Таймаут: внешний сервис не ответил.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

elif page == "Внешние запросы":
    st.header("Поиск через внешние сервисы")

    search_tab1, search_tab2 = st.tabs(["Perplexity", "Tavily"])

    with search_tab1:
        st.subheader("Поиск через Perplexity AI")
        with st.form("perplexity_search_form"):
            perp_query = st.text_input("Поисковый запрос:", placeholder="Например: Последние новости об ИИ")
            perp_submit = st.form_submit_button("Искать через Perplexity")

        if perp_submit and perp_query.strip():
            with st.spinner("Поиск через Perplexity..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/perplexity/search",
                        json={"query": perp_query.strip()},
                        timeout=180,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            st.success("Поиск завершён!")
                            st.markdown("**Ответ:**")
                            st.markdown(result.get("content", "Нет содержимого"))
                            if result.get("citations"):
                                with st.expander("Источники"):
                                    for cite in result.get("citations", []):
                                        st.write(f"- {cite}")
                        else:
                            st.error(result.get("message", "Неизвестная ошибка"))
                    else:
                        st.error(f"Ошибка API: {resp.status_code}")
                except requests.exceptions.Timeout:
                    st.error("Таймаут: Perplexity не ответил вовремя")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    with search_tab2:
        st.subheader("Поиск через Tavily")
        with st.form("tavily_search_form"):
            tav_query = st.text_input("Поисковый запрос:", placeholder="Например: Лучшие практики Python 2024")
            tav_depth = st.selectbox("Глубина поиска:", ["basic", "advanced"], format_func=lambda x: "Базовый" if x == "basic" else "Расширенный")
            tav_max = st.slider("Макс. результатов:", 1, 10, 5)
            tav_submit = st.form_submit_button("Искать через Tavily")

        if tav_submit and tav_query.strip():
            with st.spinner("Поиск через Tavily..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/tavily/search",
                        json={
                            "query": tav_query.strip(),
                            "search_depth": tav_depth,
                            "max_results": tav_max,
                            "include_answer": True,
                        },
                        timeout=180,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            st.success("Поиск завершён!")
                            if result.get("answer"):
                                st.markdown("**Ответ:**")
                                st.markdown(result.get("answer"))
                            st.markdown("**Результаты:**")
                            for item in result.get("results", []):
                                with st.expander(item.get("title", "Без заголовка")):
                                    st.write(item.get("content", ""))
                                    st.caption(item.get("url", ""))
                        else:
                            st.error(result.get("message", "Неизвестная ошибка"))
                    else:
                        st.error(f"Ошибка API: {resp.status_code}")
                except requests.exceptions.Timeout:
                    st.error("Таймаут: Tavily не ответил вовремя")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

elif page == "Утилиты":
    st.header("Панель сервисов")

    if "service_statuses" not in st.session_state:
        st.session_state.service_statuses = {}

    def check_service_status(service_name, endpoint, timeout=10):
        try:
            resp = requests.get(f"{API_BASE_URL}{endpoint}", timeout=timeout)
            if resp.status_code == 200:
                return {"status": "ok", "data": resp.json(), "latency": resp.elapsed.total_seconds()}
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Таймаут"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    st.subheader("Статус сервисов")

    if st.button("Проверить все сервисы", type="primary"):
        with st.spinner("Проверка сервисов..."):
            st.session_state.service_statuses = {
                "openrouter": check_service_status("OpenRouter LLM", "/utility/openrouter/status"),
                "perplexity": check_service_status("Perplexity", "/utility/perplexity/status"),
                "tavily": check_service_status("Tavily", "/utility/tavily/status"),
                "tarantool": check_service_status("Tarantool", "/utility/tarantool/status"),
                "health": check_service_status("Здоровье", "/utility/health"),
            }

    col1, col2, col3, col4 = st.columns(4)

    def render_status_card(col, name, key):
        with col:
            status = st.session_state.service_statuses.get(key, {})
            if not status:
                st.markdown(f"### {name}")
                st.info("Нажмите 'Проверить все сервисы'")
            elif status.get("status") == "ok":
                st.markdown(f"### {name}")
                st.success(f"ОК ({status.get('latency', 0):.2f}с)")
                data = status.get("data", {})
                if key == "openrouter":
                    st.caption(f"Модель: {data.get('model', 'Н/Д')}")
                    st.caption(f"Доступен: {'Да' if data.get('available') else 'Нет'}")
                elif key == "perplexity":
                    st.caption(f"Настроен: {'Да' if data.get('configured') else 'Нет'}")
                elif key == "tavily":
                    st.caption(f"Настроен: {'Да' if data.get('configured') else 'Нет'}")
                elif key == "tarantool":
                    st.caption(f"Режим: {data.get('mode', 'Н/Д')}")
                    cache = data.get("cache", {})
                    st.caption(f"Размер кэша: {cache.get('size', 0)}")
            else:
                st.markdown(f"### {name}")
                st.error(f"Ошибка: {status.get('error', 'Неизвестно')}")

    render_status_card(col1, "LLM (OpenRouter)", "openrouter")
    render_status_card(col2, "Perplexity", "perplexity")
    render_status_card(col3, "Tavily", "tavily")
    render_status_card(col4, "Кэш (Tarantool)", "tarantool")

    st.divider()

    st.subheader("Управление кэшем")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Очистить кэш Perplexity"):
            try:
                resp = requests.post(f"{API_BASE_URL}/utility/perplexity/cache/clear", timeout=10)
                if resp.status_code == 200:
                    st.success("Кэш Perplexity очищен!")
                else:
                    st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    with col2:
        if st.button("Очистить кэш Tavily"):
            try:
                resp = requests.post(f"{API_BASE_URL}/utility/tavily/cache/clear", timeout=10)
                if resp.status_code == 200:
                    st.success("Кэш Tavily очищен!")
                else:
                    st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    with col3:
        confirm = st.checkbox("Подтвердить полную очистку")
        if st.button("Очистить весь кэш", disabled=not confirm):
            try:
                resp = requests.get(f"{API_BASE_URL}/utility/validate_cache?confirm=true", timeout=10)
                if resp.status_code == 200:
                    st.success("Весь кэш очищен!")
                else:
                    st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.divider()

    st.subheader("Состояние системы")

    health_status = st.session_state.service_statuses.get("health", {})
    if health_status.get("status") == "ok":
        data = health_status.get("data", {})
        overall = data.get("status", "unknown")

        if overall == "healthy":
            st.success(f"Состояние системы: ЗДОРОВА")
        elif overall == "degraded":
            st.warning(f"Состояние системы: ЧАСТИЧНО РАБОТАЕТ")
            issues = data.get("issues", [])
            if issues:
                st.markdown("**Проблемы:**")
                for issue in issues:
                    st.write(f"- {issue}")
        else:
            st.error(f"Состояние системы: {overall.upper()}")

        components = data.get("components", {})
        if components:
            with st.expander("Детали компонентов"):
                st.json(components)
    else:
        st.info("Нажмите 'Проверить все сервисы' для просмотра состояния системы")
