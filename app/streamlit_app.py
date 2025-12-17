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

PAGES = ["Запрос агенту", "История", "Внешние данные", "Утилиты"]
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
    st.header("Запросы к внешним источникам")

    with st.form("external_data_form"):
        query_input = st.text_input(
            "ИНН или поисковый запрос",
            value="7707083893",
            placeholder="ИНН для DaData/Casebook/InfoSphere или текст для Perplexity/Tavily"
        )
        source = st.selectbox(
            "Источник",
            [
                ("info", "Все источники"),
                ("dadata", "DaData"),
                ("casebook", "Casebook"),
                ("infosphere", "InfoSphere"),
                ("perplexity", "Perplexity"),
                ("tavily", "Tavily"),
            ],
            format_func=lambda x: x[1],
        )
        submitted = st.form_submit_button("Получить данные")

    if submitted and query_input.strip():
        query = query_input.strip()
        source_key = source[0]

        if source_key == "info":
            st.subheader("Результаты из всех источников")
            
            with st.spinner("Запрос к DaData, Casebook, InfoSphere..."):
                try:
                    url = f"{API_BASE_URL}/data/client/info/{query}"
                    resp = requests.get(url, timeout=60)
                    if resp.status_code == 200:
                        st.success("Данные по ИНН получены")
                        with st.expander("DaData / Casebook / InfoSphere", expanded=True):
                            st.json(resp.json())
                    else:
                        st.warning(f"Ошибка ИНН-источников: {resp.status_code}")
                except Exception as e:
                    st.warning(f"Ошибка ИНН-источников: {e}")
            
            with st.spinner("Запрос к Perplexity..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/perplexity/search",
                        json={"query": query},
                        timeout=180,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            with st.expander("Perplexity", expanded=True):
                                st.markdown(result.get("content", "Нет данных"))
                                if result.get("citations"):
                                    st.caption("Источники: " + ", ".join(result.get("citations", [])))
                        else:
                            st.warning(f"Perplexity: {result.get('message', 'Ошибка')}")
                    else:
                        st.warning(f"Perplexity: HTTP {resp.status_code}")
                except Exception as e:
                    st.warning(f"Perplexity: {e}")

            with st.spinner("Запрос к Tavily..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/tavily/search",
                        json={"query": query, "max_results": 5, "include_answer": True},
                        timeout=180,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            with st.expander("Tavily", expanded=True):
                                if result.get("answer"):
                                    st.markdown(f"**Ответ:** {result.get('answer')}")
                                for item in result.get("results", []):
                                    st.markdown(f"- [{item.get('title', 'Без заголовка')}]({item.get('url', '')})")
                        else:
                            st.warning(f"Tavily: {result.get('message', 'Ошибка')}")
                    else:
                        st.warning(f"Tavily: HTTP {resp.status_code}")
                except Exception as e:
                    st.warning(f"Tavily: {e}")

        elif source_key in ("dadata", "casebook", "infosphere"):
            with st.spinner(f"Запрос к {source[1]}..."):
                try:
                    url = f"{API_BASE_URL}/data/client/{source_key}/{query}"
                    resp = requests.get(url, timeout=60)
                    if resp.status_code == 200:
                        st.success("Данные получены")
                        st.json(resp.json())
                    else:
                        st.error(f"Ошибка: {resp.status_code} - {resp.text}")
                except requests.exceptions.Timeout:
                    st.error("Таймаут: внешний сервис не ответил.")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        elif source_key == "perplexity":
            with st.spinner("Поиск через Perplexity..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/perplexity/search",
                        json={"query": query},
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

        elif source_key == "tavily":
            with st.spinner("Поиск через Tavily..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/utility/tavily/search",
                        json={"query": query, "max_results": 5, "include_answer": True},
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

    def check_service_status(service_name: str, endpoint: str, timeout: int = 10) -> dict:
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

    cols = st.columns(4)
    
    services = [
        (cols[0], "LLM (OpenRouter)", "openrouter"),
        (cols[1], "Perplexity", "perplexity"),
        (cols[2], "Tavily", "tavily"),
        (cols[3], "Кэш (Tarantool)", "tarantool"),
    ]

    for col, name, key in services:
        with col:
            status = st.session_state.service_statuses.get(key, {})
            st.markdown(f"#### {name}")
            if not status:
                st.info("Ожидание")
            elif status.get("status") == "ok":
                latency = status.get("latency", 0)
                st.success(f"ОК ({latency:.2f}с)")
                data = status.get("data", {})
                if key == "openrouter":
                    st.caption(f"Модель: {data.get('model', 'Н/Д')}")
                elif key == "perplexity":
                    st.caption(f"Настроен: {'Да' if data.get('configured') else 'Нет'}")
                elif key == "tavily":
                    st.caption(f"Настроен: {'Да' if data.get('configured') else 'Нет'}")
                elif key == "tarantool":
                    st.caption(f"Режим: {data.get('mode', 'Н/Д')}")
                    cache = data.get("cache", {})
                    st.caption(f"Записей: {cache.get('size', 0)}")
            else:
                st.error(f"{status.get('error', 'Ошибка')}")

    st.divider()

    st.subheader("Управление кэшем Tarantool")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Очистить кэш Tarantool"):
            try:
                resp = requests.delete(f"{API_BASE_URL}/utility/cache/prefix/search:", timeout=10)
                if resp.status_code == 200:
                    st.success("Кэш Tarantool очищен!")
                else:
                    st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    with col2:
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
            st.success("Состояние системы: ЗДОРОВА")
        elif overall == "degraded":
            st.warning("Состояние системы: ЧАСТИЧНО РАБОТАЕТ")
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
