import os
import re
import time

import requests
import streamlit as st

st.set_page_config(
    page_title="Система анализа контрагентов",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stToolbar"] {
        display: none !important;
    }
    .stDeployButton {
        display: none !important;
    }
    #MainMenu {
        display: none !important;
    }
    /* ВАЖНО: не скрываем stHeader полностью, иначе пропадает кнопка
       сворачивания/разворачивания боковой панели. */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    footer {
        display: none !important;
    }
    
    /* Кнопка открытия боковой панели */
    [data-testid="stSidebarCollapsedControl"] {
        display: flex !important;
        visibility: visible !important;
    }
    
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
    }
    
    button[kind="header"] {
        display: flex !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Система анализа контрагентов")

BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
API_BASE_URL = f"http://localhost:{BACKEND_PORT}"

def validate_inn(inn: str) -> tuple[bool, str]:
    if not inn:
        return False, "ИНН не может быть пустым"
    if not re.match(r'^\d+$', inn):
        return False, "ИНН должен содержать только цифры"
    if len(inn) not in (10, 12):
        return False, "ИНН должен содержать 10 или 12 цифр"
    return True, ""

def request_with_retry(method: str, url: str, max_retries: int = 3, initial_timeout: int = 60, **kwargs) -> requests.Response:
    timeouts = [initial_timeout, initial_timeout * 2, initial_timeout * 4]
    max_timeout = 600
    
    last_error = None
    for attempt in range(max_retries):
        timeout = min(timeouts[attempt] if attempt < len(timeouts) else timeouts[-1], max_timeout)
        try:
            if method.lower() == "get":
                return requests.get(url, timeout=timeout, **kwargs)
            elif method.lower() == "post":
                return requests.post(url, timeout=timeout, **kwargs)
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < max_retries - 1:
                st.warning(f"Попытка {attempt + 1}/{max_retries} не удалась (таймаут {timeout}с). Повторяем...")
                time.sleep(1)
            continue
        except Exception as e:
            raise e
    
    raise last_error or requests.exceptions.Timeout("Все попытки исчерпаны")

if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "last_thread_id" not in st.session_state:
    st.session_state.last_thread_id = None
if "threads" not in st.session_state:
    st.session_state.threads = []
if "page" not in st.session_state:
    st.session_state.page = "Запрос агенту"
if "admin_token" not in st.session_state:
    st.session_state.admin_token = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

st.sidebar.title("Навигация")

st.sidebar.subheader("Авторизация")
admin_token = st.sidebar.text_input(
    "Токен администратора",
    type="password",
    value=st.session_state.admin_token,
    key="global_admin_token",
    help="Введите ADMIN_TOKEN для доступа к административным функциям"
)
if admin_token != st.session_state.admin_token:
    st.session_state.admin_token = admin_token
    try:
        resp = requests.get(
            f"{API_BASE_URL}/utility/auth/role",
            headers={"X-Auth-Token": admin_token},
            timeout=5
        )
        if resp.status_code == 200:
            role_data = resp.json()
            st.session_state.is_admin = role_data.get("is_admin", False)
        else:
            st.session_state.is_admin = False
    except:
        st.session_state.is_admin = False

if st.session_state.is_admin:
    st.sidebar.success("Администратор")
elif st.session_state.admin_token:
    st.sidebar.warning("Неверный токен")

st.sidebar.divider()

PAGES_BASE = ["Запрос агенту", "История", "Внешние данные"]
PAGES_ADMIN = ["Утилиты", "Метрики", "Логи"]

if st.session_state.is_admin:
    PAGES = PAGES_BASE + PAGES_ADMIN
else:
    PAGES = PAGES_BASE

if st.session_state.page not in PAGES:
    st.session_state.page = PAGES[0]

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

    tab_inn, tab_search = st.tabs(["По ИНН", "Поисковые запросы"])

    with tab_inn:
        st.subheader("Запросы по ИНН")
        st.caption("DaData, Casebook, InfoSphere - требуют валидный ИНН (10 или 12 цифр)")

        with st.form("inn_data_form"):
            inn_input = st.text_input(
                "ИНН компании",
                value="7707083893",
                max_chars=12,
                placeholder="Введите 10 или 12 цифр ИНН"
            )
            inn_source = st.selectbox(
                "Источник",
                [
                    ("info", "Все источники (DaData + Casebook + InfoSphere)"),
                    ("dadata", "DaData"),
                    ("casebook", "Casebook"),
                    ("infosphere", "InfoSphere"),
                ],
                format_func=lambda x: x[1],
            )
            inn_submitted = st.form_submit_button("Получить данные по ИНН")

        if inn_submitted:
            inn = inn_input.strip()
            is_valid, error_msg = validate_inn(inn)
            
            if not is_valid:
                st.error(f"Ошибка валидации: {error_msg}")
            else:
                source_key = inn_source[0]
                with st.spinner(f"Запрос к {inn_source[1]}..."):
                    try:
                        url = f"{API_BASE_URL}/data/client/{source_key}/{inn}"
                        resp = request_with_retry("get", url, max_retries=3, initial_timeout=60)
                        if resp.status_code == 200:
                            st.success("Данные получены")
                            st.json(resp.json())
                        else:
                            st.error(f"Ошибка: {resp.status_code} - {resp.text}")
                    except requests.exceptions.Timeout:
                        st.error("Таймаут: все 3 попытки исчерпаны (макс. 10 мин)")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

    with tab_search:
        st.subheader("Поисковые запросы")
        st.caption("Perplexity, Tavily - поиск информации о компании по ИНН. Возвращает только проверенные факты.")

        with st.form("search_data_form"):
            search_inn = st.text_input(
                "ИНН компании",
                value="7707083893",
                max_chars=12,
                placeholder="Введите 10 или 12 цифр ИНН",
                help="ИНН компании для поиска (10 цифр - юр.лицо, 12 цифр - ИП)"
            )
            search_query = st.text_input(
                "Что искать",
                placeholder="Например: судебные дела, банкротство, новости",
                help="Укажите тему поиска. Результаты будут содержать только факты."
            )
            search_source = st.selectbox(
                "Поисковый сервис",
                [
                    ("all_search", "Все поисковики (Perplexity + Tavily)"),
                    ("perplexity", "Perplexity"),
                    ("tavily", "Tavily"),
                ],
                format_func=lambda x: x[1],
            )
            search_submitted = st.form_submit_button("Выполнить поиск")

        if search_submitted:
            inn = search_inn.strip()
            query = search_query.strip()
            
            is_valid, error_msg = validate_inn(inn)
            if not is_valid:
                st.error(f"Ошибка ИНН: {error_msg}")
            elif not query:
                st.error("Укажите что искать (например: судебные дела, банкротство)")
            else:
                source_key = search_source[0]
                
                if source_key == "all_search":
                    st.subheader("Результаты поиска")
                    headers = {"X-Auth-Token": st.session_state.get("admin_token", "")}
                    
                    with st.spinner("Поиск через Perplexity..."):
                        try:
                            resp = request_with_retry(
                                "post",
                                f"{API_BASE_URL}/data/search/perplexity",
                                max_retries=3,
                                initial_timeout=90,
                                json={"inn": inn, "search_query": query},
                                headers=headers
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
                        except requests.exceptions.Timeout:
                            st.warning("Perplexity: таймаут (все попытки исчерпаны)")
                        except Exception as e:
                            st.warning(f"Perplexity: {e}")

                    with st.spinner("Поиск через Tavily..."):
                        try:
                            resp = request_with_retry(
                                "post",
                                f"{API_BASE_URL}/data/search/tavily",
                                max_retries=3,
                                initial_timeout=60,
                                json={"inn": inn, "search_query": query, "max_results": 5, "include_answer": True},
                                headers=headers
                            )
                            if resp.status_code == 200:
                                result = resp.json()
                                if result.get("status") == "success":
                                    with st.expander("Tavily", expanded=True):
                                        if result.get("answer"):
                                            st.markdown(f"**Ответ:** {result.get('answer')}")
                                        for item in result.get("results", []):
                                            title = item.get("title", "Без заголовка")
                                            content = item.get("content", "") or item.get("snippet", "")
                                            st.markdown(f"**{title}**")
                                            if content:
                                                st.caption(content[:300] + "..." if len(content) > 300 else content)
                                else:
                                    st.warning(f"Tavily: {result.get('message', 'Ошибка')}")
                            else:
                                st.warning(f"Tavily: HTTP {resp.status_code}")
                        except requests.exceptions.Timeout:
                            st.warning("Tavily: таймаут (все попытки исчерпаны)")
                        except Exception as e:
                            st.warning(f"Tavily: {e}")

                elif source_key == "perplexity":
                    headers = {"X-Auth-Token": st.session_state.get("admin_token", "")}
                    with st.spinner("Поиск через Perplexity..."):
                        try:
                            resp = request_with_retry(
                                "post",
                                f"{API_BASE_URL}/data/search/perplexity",
                                max_retries=3,
                                initial_timeout=90,
                                json={"inn": inn, "search_query": query},
                                headers=headers
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
                            st.error("Таймаут: все 3 попытки исчерпаны")
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

                elif source_key == "tavily":
                    headers = {"X-Auth-Token": st.session_state.get("admin_token", "")}
                    with st.spinner("Поиск через Tavily..."):
                        try:
                            resp = request_with_retry(
                                "post",
                                f"{API_BASE_URL}/data/search/tavily",
                                max_retries=3,
                                initial_timeout=60,
                                json={"inn": inn, "search_query": query, "max_results": 5, "include_answer": True},
                                headers=headers
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
                            st.error("Таймаут: все 3 попытки исчерпаны")
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
                return {
                    "status": "ok",
                    "service_name": service_name,
                    "data": resp.json(),
                    "latency": resp.elapsed.total_seconds(),
                }
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        except requests.exceptions.Timeout:
            return {"status": "error", "service_name": service_name, "error": "Таймаут"}
        except Exception as e:
            return {"status": "error", "service_name": service_name, "error": str(e)}

    st.subheader("Статус сервисов")

    if st.button("Проверить все сервисы", type="primary"):
        with st.spinner("Проверка сервисов..."):
            st.session_state.service_statuses = {
                "openrouter": check_service_status("OpenRouter LLM", "/utility/openrouter/status"),
                "perplexity": check_service_status("Perplexity", "/utility/perplexity/status"),
                "tavily": check_service_status("Tavily", "/utility/tavily/status"),
                "tarantool": check_service_status("Tarantool", "/utility/tarantool/status"),
                "email": check_service_status("Email", "/utility/email/status"),
                "health": check_service_status("Здоровье", "/utility/health"),
            }

    with st.container(border=True):
        st.markdown("##### Основные сервисы")
        cols = st.columns(3)
        
        services = [
            (cols[0], "LLM (OpenRouter)", "openrouter"),
            (cols[1], "Perplexity", "perplexity"),
            (cols[2], "Tavily", "tavily"),
        ]

        for col, name, key in services:
            with col:
                status = st.session_state.service_statuses.get(key, {})
                st.markdown(f"**{name}**")
                if not status:
                    st.info("Ожидание")
                elif status.get("status") == "ok":
                    latency = status.get("latency", 0)
                    st.success(f"ОК ({latency:.2f}с)")
                    data = status.get("data", {})
                    if key == "openrouter":
                        st.caption(f"Модель: {data.get('model', 'Н/Д')}")
                    elif key == "perplexity":
                        st.caption(f"Доступен: {'Да' if data.get('available') else 'Нет'}")
                    elif key == "tavily":
                        st.caption(f"Доступен: {'Да' if data.get('available') else 'Нет'}")
                else:
                    st.error(f"{status.get('error', 'Ошибка')}")

    with st.container(border=True):
        st.markdown("##### Инфраструктура")
        cols2 = st.columns(2)
        
        infra_services = [
            (cols2[0], "Кэш (Tarantool)", "tarantool"),
            (cols2[1], "Email (SMTP)", "email"),
        ]

        for col, name, key in infra_services:
            with col:
                status = st.session_state.service_statuses.get(key, {})
                st.markdown(f"**{name}**")
                if not status:
                    st.info("Ожидание")
                elif status.get("status") == "ok":
                    latency = status.get("latency", 0)
                    st.success(f"ОК ({latency:.2f}с)")
                    data = status.get("data", {})
                    if key == "tarantool":
                        st.caption(f"Режим: {data.get('mode', 'Н/Д')}")
                        cache = data.get("cache", {})
                        st.caption(f"Записей: {cache.get('size', 0)}")
                    elif key == "email":
                        health = data.get("health", {})
                        email_status = health.get("status", "unknown")
                        if email_status == "not_configured":
                            st.caption("SMTP не настроен")
                        else:
                            st.caption(f"SMTP: {data.get('smtp_host', 'Н/Д')}")
                else:
                    st.warning(f"{status.get('error', 'Не доступен')}")

    st.divider()

    st.subheader("Управление кэшем")

    if not st.session_state.is_admin:
        st.info("Для управления кэшем необходимы права администратора. Введите токен в боковой панели.")
    else:
        headers = {"X-Auth-Token": st.session_state.admin_token}
        
        with st.container(border=True):
            st.markdown("##### Записи в кэше (первые 10)")
            if st.button("Загрузить записи кэша"):
                try:
                    resp = requests.get(
                        f"{API_BASE_URL}/utility/cache/entries?limit=10",
                        headers=headers,
                        timeout=15
                    )
                    if resp.status_code == 200:
                        cache_data = resp.json()
                        entries = cache_data.get("entries", [])
                        if entries:
                            for entry in entries:
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    st.text(entry.get("key", "N/A")[:50])
                                with col2:
                                    size = entry.get("size_bytes", 0)
                                    st.text(f"{size} байт")
                                with col3:
                                    expires = entry.get("expires_in", 0)
                                    st.text(f"{expires}с")
                        else:
                            st.info("Кэш пуст")
                    elif resp.status_code == 403:
                        st.error("Доступ запрещён")
                    else:
                        st.error(f"Ошибка: {resp.status_code}")
                except Exception as e:
                    st.error(f"Ошибка: {e}")
        
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Очистить кэш поиска"):
                try:
                    resp = requests.delete(
                        f"{API_BASE_URL}/utility/cache/prefix/search:",
                        headers=headers,
                        timeout=10
                    )
                    if resp.status_code == 200:
                        st.success("Кэш поиска очищен!")
                    elif resp.status_code == 403:
                        st.error("Доступ запрещён. Проверьте токен.")
                    else:
                        st.error(f"Ошибка: {resp.status_code}")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        with col2:
            confirm = st.checkbox("Подтвердить полную очистку")
            if st.button("Очистить весь кэш", disabled=not confirm):
                try:
                    resp = requests.get(
                        f"{API_BASE_URL}/utility/validate_cache?confirm=true",
                        headers=headers,
                        timeout=10
                    )
                    if resp.status_code == 200:
                        st.success("Весь кэш очищен!")
                    elif resp.status_code == 403:
                        st.error("Доступ запрещён. Проверьте токен.")
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

    st.divider()

    st.subheader("Отчёты PDF")

    try:
        resp = requests.get(f"{API_BASE_URL}/utility/reports/list", timeout=10)
        if resp.status_code == 200:
            reports_data = resp.json()
            reports = reports_data.get("reports", [])
            
            if reports:
                st.write(f"Найдено отчётов: {len(reports)}")
                for report in reports[:10]:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.text(report.get("filename", "Без имени"))
                    with col2:
                        size_kb = report.get("size_bytes", 0) / 1024
                        st.text(f"{size_kb:.1f} KB")
                    with col3:
                        download_url = f"{API_BASE_URL}{report.get('download_url', '')}"
                        st.download_button(
                            label="Скачать",
                            data=requests.get(download_url, timeout=10).content if download_url else b"",
                            file_name=report.get("filename", "report.pdf"),
                            mime="application/pdf",
                            key=f"dl_{report.get('filename', 'report')}"
                        )
            else:
                st.info("Нет сохранённых отчётов")
    except Exception as e:
        st.warning(f"Не удалось загрузить список отчётов: {e}")

elif page == "Метрики":
    st.header("Панель метрик администратора")
    
    if st.session_state.is_admin:
        headers = {"X-Auth-Token": st.session_state.admin_token}
        
        col_refresh, col_reset = st.columns(2)
        with col_refresh:
            refresh_metrics = st.button("Обновить метрики", type="primary")
        with col_reset:
            reset_metrics = st.button("Сбросить метрики", type="secondary")
        
        if reset_metrics:
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/utility/metrics/reset",
                    headers=headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    st.success("Метрики сброшены")
                else:
                    st.error(f"Ошибка сброса: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("HTTP клиент")
            try:
                resp = requests.get(f"{API_BASE_URL}/utility/metrics", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    metrics = data.get("metrics", {})
                    
                    if metrics:
                        total_requests = 0
                        total_errors = 0
                        
                        for service, service_metrics in metrics.items():
                            if isinstance(service_metrics, dict):
                                total_requests += service_metrics.get("total_requests", 0)
                                total_errors += service_metrics.get("errors", 0)
                        
                        metric_col1, metric_col2, metric_col3 = st.columns(3)
                        with metric_col1:
                            st.metric("Всего запросов", total_requests)
                        with metric_col2:
                            st.metric("Ошибок", total_errors)
                        with metric_col3:
                            error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
                            st.metric("Ошибок %", f"{error_rate:.1f}%")
                        
                        with st.expander("Детали по сервисам"):
                            for service, service_metrics in metrics.items():
                                if isinstance(service_metrics, dict):
                                    st.markdown(f"**{service}**")
                                    st.json(service_metrics)
                    else:
                        st.info("Нет данных о метриках HTTP")
                else:
                    st.error(f"Ошибка загрузки: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")
        
        with col2:
            st.subheader("Кэш (Tarantool)")
            try:
                resp = requests.get(f"{API_BASE_URL}/utility/cache/metrics", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    metrics = data.get("metrics", {})
                    cache_size = data.get("cache_size", 0)
                    
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    with metric_col1:
                        st.metric("Записей", cache_size)
                    with metric_col2:
                        hits = metrics.get("hits", 0)
                        misses = metrics.get("misses", 0)
                        hit_rate = metrics.get("hit_rate", 0)
                        st.metric("Hit Rate", f"{hit_rate:.1f}%")
                    with metric_col3:
                        st.metric("Hits / Misses", f"{hits} / {misses}")
                    
                    config = data.get("config", {})
                    if config:
                        with st.expander("Конфигурация кэша"):
                            st.json(config)
                else:
                    st.error(f"Ошибка загрузки: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")
        
        st.divider()
        
        st.subheader("Circuit Breakers")
        try:
            resp = requests.get(f"{API_BASE_URL}/utility/circuit-breakers", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                breakers = data.get("circuit_breakers", {})
                
                if breakers:
                    cols = st.columns(min(len(breakers), 4))
                    for idx, (service, cb_data) in enumerate(breakers.items()):
                        with cols[idx % 4]:
                            state = cb_data.get("state", "unknown") if isinstance(cb_data, dict) else "unknown"
                            if state == "closed":
                                st.success(f"{service}: ЗАКРЫТ")
                            elif state == "open":
                                st.error(f"{service}: ОТКРЫТ")
                            elif state == "half_open":
                                st.warning(f"{service}: ПОЛУОТКРЫТ")
                            else:
                                st.info(f"{service}: {state}")
                            
                            if st.button(f"Сбросить", key=f"reset_cb_{service}"):
                                try:
                                    reset_resp = requests.post(
                                        f"{API_BASE_URL}/utility/circuit-breakers/{service}/reset",
                                        headers=headers,
                                        timeout=10
                                    )
                                    if reset_resp.status_code == 200:
                                        st.success("Сброшен!")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                else:
                    st.info("Нет активных circuit breakers")
            else:
                st.error(f"Ошибка загрузки: {resp.status_code}")
        except Exception as e:
            st.error(f"Ошибка: {e}")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.subheader("Email (SMTP)")
                try:
                    resp = requests.get(f"{API_BASE_URL}/utility/email/status", timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        
                        metric_col1, metric_col2 = st.columns(2)
                        with metric_col1:
                            configured = data.get("configured", False)
                            if configured:
                                st.success("Настроен")
                            else:
                                st.warning("Не настроен")
                        with metric_col2:
                            smtp_host = data.get("smtp_host", "Н/Д")
                            st.caption(f"SMTP: {smtp_host}")
                    else:
                        st.warning("Сервис недоступен")
                except Exception as e:
                    st.error(f"Ошибка: {e}")
        
        with col2:
            with st.container(border=True):
                st.subheader("OpenTelemetry Трейсы")
                try:
                    resp = requests.get(
                        f"{API_BASE_URL}/utility/traces/stats",
                        headers=headers,
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        stats = data.get("stats", {})
                        
                        metric_col1, metric_col2, metric_col3 = st.columns(3)
                        with metric_col1:
                            st.metric("Всего спанов", stats.get("total_spans", 0))
                        with metric_col2:
                            st.metric("Ср. время (мс)", stats.get("avg_duration_ms", 0))
                        with metric_col3:
                            st.metric("Ошибок", stats.get("error_count", 0))
                        
                        by_kind = stats.get("by_kind", {})
                        if by_kind:
                            with st.expander("По типу"):
                                for kind, count in by_kind.items():
                                    st.caption(f"{kind}: {count}")
                    else:
                        st.warning("Трейсы недоступны")
                except Exception as e:
                    st.error(f"Ошибка: {e}")
        
        st.divider()
        
        st.subheader("Последние трейсы")
        try:
            resp = requests.get(
                f"{API_BASE_URL}/utility/traces?limit=20",
                headers=headers,
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                spans = data.get("spans", [])
                
                if spans:
                    for span in spans[:10]:
                        status_icon = "🟢" if span.get("status") == "OK" else "🔴" if span.get("status") == "ERROR" else "⚪"
                        duration = span.get("duration_ms", 0)
                        name = span.get("name", "unknown")
                        
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.caption(f"{status_icon} {name}")
                        with col2:
                            st.caption(f"{duration:.1f}мс")
                        with col3:
                            st.caption(span.get("start_time", "")[:19])
                else:
                    st.info("Нет трейсов")
            else:
                st.warning("Не удалось загрузить трейсы")
        except Exception as e:
            st.error(f"Ошибка: {e}")

elif page == "Логи":
    st.header("Просмотр логов приложения")
    
    if st.session_state.is_admin:
        headers = {"X-Auth-Token": st.session_state.admin_token}
        
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                since_minutes = st.selectbox(
                    "Период",
                    options=[5, 15, 30, 60, 120, 0],
                    format_func=lambda x: f"Последние {x} мин" if x > 0 else "Все логи",
                    index=1
                )
            
            with col2:
                level_filter = st.selectbox(
                    "Уровень",
                    options=["", "DEBUG", "INFO", "WARNING", "ERROR"],
                    format_func=lambda x: x if x else "Все уровни"
                )
            
            with col3:
                limit = st.number_input("Лимит", min_value=10, max_value=500, value=100)
            
            with col4:
                st.write("")
                st.write("")
                refresh_logs = st.button("Обновить", type="primary")
        
        params = {"limit": limit}
        if since_minutes > 0:
            params["since_minutes"] = since_minutes
        if level_filter:
            params["level"] = level_filter
        
        try:
            resp = requests.get(
                f"{API_BASE_URL}/utility/logs",
                headers=headers,
                params=params,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                logs = data.get("logs", [])
                stats = data.get("stats", {})
                
                with st.container(border=True):
                    st.subheader("Статистика")
                    stat_cols = st.columns(5)
                    
                    levels = ["total", "DEBUG", "INFO", "WARNING", "ERROR"]
                    colors = {"total": "📊", "DEBUG": "🔍", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌"}
                    
                    for idx, level in enumerate(levels):
                        with stat_cols[idx]:
                            count = stats.get(level, 0)
                            st.metric(f"{colors.get(level, '')} {level}", count)
                
                st.divider()
                
                st.subheader(f"Логи ({len(logs)} записей)")
                
                if logs:
                    for log in logs:
                        level = log.get("level", "INFO")
                        timestamp = log.get("timestamp", "")[:19]
                        message = log.get("message", "")
                        logger_name = log.get("logger", "")
                        
                        if level == "ERROR":
                            color = "🔴"
                        elif level == "WARNING":
                            color = "🟡"
                        elif level == "DEBUG":
                            color = "⚪"
                        else:
                            color = "🟢"
                        
                        with st.container(border=True):
                            col1, col2 = st.columns([1, 5])
                            with col1:
                                st.caption(f"{color} {level}")
                                st.caption(timestamp)
                            with col2:
                                st.text(message[:200] + ("..." if len(message) > 200 else ""))
                                if logger_name:
                                    st.caption(f"Logger: {logger_name}")
                else:
                    st.info("Нет логов за выбранный период")
                
                st.divider()
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Очистить логи", type="secondary"):
                        try:
                            clear_resp = requests.post(
                                f"{API_BASE_URL}/utility/logs/clear",
                                headers=headers,
                                timeout=10
                            )
                            if clear_resp.status_code == 200:
                                st.success("Логи очищены")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
            else:
                st.error(f"Ошибка загрузки: {resp.status_code}")
        except Exception as e:
            st.error(f"Ошибка: {e}")

