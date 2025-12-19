import os
import re
import time

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Система анализа контрагентов",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Скрываем элементы Streamlit UI */
    [data-testid="stToolbar"] {
        display: none !important;
    }
    .stDeployButton {
        display: none !important;
    }
    #MainMenu {
        display: none !important;
    }
    footer {
        display: none !important;
    }
    
    /* Сохраняем header для корректной работы sidebar */
    header[data-testid="stHeader"] {
        background: transparent !important;
        visibility: visible !important;
    }
    
    /* Фиксим отображение боковой панели */
    section[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
    }
    
    /* Кнопка открытия/закрытия боковой панели */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    button[kind="header"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* Улучшаем стиль боковой панели: читаемость и контраст */
    section[data-testid="stSidebar"] {
        background-color: #111827 !important;
        color: #e5e7eb !important;
    }
    section[data-testid="stSidebar"] > div {
        background-color: transparent !important;
        padding: 1.5rem 1rem;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] .st-cq,
    section[data-testid="stSidebar"] .st-cn {
        color: #e5e7eb !important;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea,
    section[data-testid="stSidebar"] select {
        background-color: #0b1221 !important;
        color: #f9fafb !important;
        border-radius: 6px !important;
        border: 1px solid #1f2937 !important;
    }
    section[data-testid="stSidebar"] .stButton button,
    section[data-testid="stSidebar"] .stDownloadButton button,
    section[data-testid="stSidebar"] .stLinkButton button {
        background-color: #1f2937 !important;
        color: #f9fafb !important;
        border: 1px solid #374151 !important;
    }
    section[data-testid="stSidebar"] .stRadio > label {
        font-weight: 700;
        font-size: 1.05rem;
        color: #f9fafb !important;
    }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        color: #e5e7eb !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Система анализа контрагентов")

BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
# Prefer explicit API_BASE_URL (for deployments / reverse proxies).
# Fallback: local backend + versioned API.
API_BASE_URL = (os.getenv("API_BASE_URL") or f"http://localhost:{BACKEND_PORT}/api/v1").rstrip("/")

def validate_inn_frontend(inn: str) -> tuple[bool, str]:
    """Валидация ИНН на фронтенде (импортируем из helpers)."""
    try:
        # Импортируем функцию валидации из backend
        import sys
        sys.path.insert(0, '/app')
        from app.utility.helpers import validate_inn
        return validate_inn(inn)
    except ImportError:
        # Fallback на простую проверку если импорт не удался
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

def _get_request_id_from_response(resp: requests.Response) -> str:
    return resp.headers.get("X-Request-ID") or resp.headers.get("x-request-id") or ""

def _show_api_error(resp: requests.Response, prefix: str = "Ошибка API"):
    rid = _get_request_id_from_response(resp)
    details = None
    try:
        details = resp.json()
    except Exception:
        details = resp.text
    if rid:
        st.error(f"{prefix}: HTTP {resp.status_code} (request_id={rid})")
    else:
        st.error(f"{prefix}: HTTP {resp.status_code}")
    st.caption(details)

if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "last_thread_id" not in st.session_state:
    st.session_state.last_thread_id = None
if "threads" not in st.session_state:
    st.session_state.threads = []
if "page" not in st.session_state:
    st.session_state.page = "Запрос агенту"
if "admin_token" not in st.session_state:
    st.session_state.admin_token = os.getenv("ADMIN_TOKEN", "")
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "admin_checked" not in st.session_state:
    st.session_state.admin_checked = False
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = API_BASE_URL

st.sidebar.title("Навигация")

st.sidebar.subheader("API")
api_base_url_input = st.sidebar.text_input(
    "API Base URL",
    value=st.session_state.api_base_url,
    help="Например: http://localhost:8000/api/v1 или https://api.example.com/api/v1",
)
st.session_state.api_base_url = (api_base_url_input or "").rstrip("/")
API_BASE_URL = st.session_state.api_base_url

if st.sidebar.button("Проверить API"):
    try:
        r = requests.get(f"{API_BASE_URL}/utility/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            st.sidebar.success(f"OK: {data.get('status')}")
            issues = data.get("issues") or []
            if issues:
                st.sidebar.caption("\n".join(issues[:5]))
        else:
            _show_api_error(r, prefix="Healthcheck failed")
    except Exception as e:
        st.sidebar.error(f"API недоступен: {e}")

st.sidebar.subheader("Авторизация")
admin_token = st.sidebar.text_input(
    "Токен администратора",
    type="password",
    value=st.session_state.admin_token,
    key="global_admin_token",
    help="Введите ADMIN_TOKEN для доступа к административным функциям"
)
def _check_admin(token: str):
    if not token:
        st.session_state.is_admin = False
        st.session_state.admin_checked = True
        return
    try:
        resp = requests.get(
            f"{API_BASE_URL}/utility/auth/role",
            headers={"X-Auth-Token": token},
            timeout=5
        )
        if resp.status_code == 200:
            role_data = resp.json()
            st.session_state.is_admin = role_data.get("is_admin", False)
        else:
            st.session_state.is_admin = False
            _show_api_error(resp, prefix="Auth check failed")
        st.session_state.admin_checked = True
    except Exception as e:
        st.session_state.is_admin = False
        st.session_state.admin_checked = True
        st.sidebar.error(f"Auth error: {e}")

if admin_token != st.session_state.admin_token:
    st.session_state.admin_token = admin_token
    _check_admin(admin_token)
elif st.session_state.admin_token and not st.session_state.admin_checked:
    _check_admin(st.session_state.admin_token)

if st.session_state.is_admin:
    st.sidebar.success("Администратор")
elif st.session_state.admin_token:
    st.sidebar.warning("Неверный токен")

st.sidebar.divider()

PAGES_BASE = ["Запрос агенту", "Внешние запросы"]
PAGES_ADMIN = ["Утилиты"]

PAGES = PAGES_BASE + PAGES_ADMIN if st.session_state.is_admin else PAGES_BASE

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
                    _show_api_error(response, prefix="Ошибка сервера")
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

elif page == "Внешние запросы":
    st.header("Внешние запросы")

    st.markdown("### Вызов внешних API")
    st.caption("DaData, Casebook, InfoSphere — требуют валидный ИНН (10 или 12 цифр)")

    with st.container(border=True):
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
            is_valid, error_msg = validate_inn_frontend(inn)
            
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

    st.markdown("### Вызов поисковых сервисов")
    st.caption("Perplexity, Tavily — поиск информации о компании по ИНН, только проверенные факты.")

    with st.container(border=True):
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
            
            is_valid, error_msg = validate_inn_frontend(inn)
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
    st.header("Админские утилиты")

    if not st.session_state.is_admin:
        st.warning("Доступ только для администратора. Укажите токен в сайдбаре.")
        st.stop()

    headers = {"X-Auth-Token": st.session_state.admin_token}
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

    st.subheader("Чеки сервисов")
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
    st.subheader("Кэш и ключи")

    with st.container(border=True):
        st.markdown("##### Первые 10 ключей")
        if st.button("Показать ключи кэша"):
            try:
                resp = requests.get(
                    f"{API_BASE_URL}/utility/cache/entries?limit=10",
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    entries = resp.json().get("entries", [])
                    if entries:
                        for entry in entries:
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.text(entry.get("key", "N/A")[:60])
                            with col2:
                                st.caption(f"{entry.get('size_bytes', 0)} байт")
                            with col3:
                                st.caption(f"{entry.get('expires_in', 0)}с")
                    else:
                        st.info("Кэш пуст")
                else:
                    _show_api_error(resp, prefix="Кэш недоступен")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    col_cache_left, col_cache_right = st.columns(2)
    with col_cache_left:
        if st.button("Очистить кэш поиска"):
            try:
                resp = requests.delete(
                    f"{API_BASE_URL}/utility/cache/prefix/search:",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Кэш поиска очищен!")
                else:
                    _show_api_error(resp, prefix="Ошибка очистки поиска")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with col_cache_right:
        confirm_wipe = st.checkbox("Подтверждаю полную очистку кэша")
        if st.button("Очистить весь кэш", disabled=not confirm_wipe):
            try:
                resp = requests.get(
                    f"{API_BASE_URL}/utility/validate_cache?confirm=true",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Весь кэш очищен")
                else:
                    _show_api_error(resp, prefix="Ошибка очистки кэша")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    extra_cache_col1, extra_cache_col2 = st.columns(2)
    with extra_cache_col1:
        if st.button("Очистить Tavily кэш"):
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/utility/tavily/cache/clear",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Tavily кэш очищен")
                else:
                    _show_api_error(resp, prefix="Tavily кэш")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with extra_cache_col2:
        if st.button("Очистить Perplexity кэш"):
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/utility/perplexity/cache/clear",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Perplexity кэш очищен")
                else:
                    _show_api_error(resp, prefix="Perplexity кэш")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.divider()
    st.subheader("Метрики")

    col_metrics, col_cache_metrics = st.columns(2)
    with col_metrics:
        reset_metrics = st.button("Сбросить HTTP метрики", type="secondary")
        try:
            resp = requests.get(f"{API_BASE_URL}/utility/metrics", timeout=10)
            if resp.status_code == 200:
                metrics = resp.json().get("metrics", {})
                total_requests = sum(m.get("total_requests", 0) for m in metrics.values() if isinstance(m, dict))
                total_errors = sum(m.get("errors", 0) for m in metrics.values() if isinstance(m, dict))
                err_rate = (total_errors / total_requests * 100) if total_requests else 0
                mcol1, mcol2, mcol3 = st.columns(3)
                with mcol1:
                    st.metric("Всего запросов", total_requests)
                with mcol2:
                    st.metric("Ошибок", total_errors)
                with mcol3:
                    st.metric("Ошибок %", f"{err_rate:.1f}%")
                if metrics:
                    with st.expander("Детализация по сервисам"):
                        st.json(metrics)
            else:
                _show_api_error(resp, prefix="Метрики HTTP")
        except Exception as e:
            st.error(f"Ошибка: {e}")
        if reset_metrics:
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/utility/metrics/reset",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Метрики сброшены")
                else:
                    _show_api_error(resp, prefix="Сброс метрик")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    with col_cache_metrics:
        try:
            resp = requests.get(f"{API_BASE_URL}/utility/cache/metrics", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                cache_size = data.get("cache_size", 0)
                metrics = data.get("metrics", {})
                hits = metrics.get("hits", 0)
                misses = metrics.get("misses", 0)
                hit_rate = metrics.get("hit_rate", 0)
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Записей", cache_size)
                with c2:
                    st.metric("Hit rate", f"{hit_rate:.1f}%")
                with c3:
                    st.metric("Hits/Misses", f"{hits}/{misses}")
                if data.get("config"):
                    with st.expander("Конфигурация кэша"):
                        st.json(data.get("config"))
            else:
                _show_api_error(resp, prefix="Метрики кэша")
        except Exception as e:
            st.error(f"Ошибка: {e}")
        if st.button("Сбросить метрики кэша", type="secondary"):
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/utility/cache/metrics/reset",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success("Метрики кэша сброшены")
                else:
                    _show_api_error(resp, prefix="Сброс метрик кэша")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    st.divider()
    st.subheader("Трейсы (OpenTelemetry)")

    with st.container(border=True):
        try:
            resp = requests.get(
                f"{API_BASE_URL}/utility/traces/stats",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                stats = resp.json().get("stats", {})
                t1, t2, t3 = st.columns(3)
                with t1:
                    st.metric("Всего спанов", stats.get("total_spans", 0))
                with t2:
                    st.metric("Среднее (мс)", stats.get("avg_duration_ms", 0))
                with t3:
                    st.metric("Ошибок", stats.get("error_count", 0))
                if stats.get("by_kind"):
                    with st.expander("По типу"):
                        for kind, count in stats.get("by_kind", {}).items():
                            st.caption(f"{kind}: {count}")
            else:
                _show_api_error(resp, prefix="Статистика трейсов")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    with st.container(border=True):
        try:
            resp = requests.get(
                f"{API_BASE_URL}/utility/traces",
                headers=headers,
                params={"limit": 20},
                timeout=10,
            )
            if resp.status_code == 200:
                spans = resp.json().get("spans", [])
                if spans:
                    for span in spans[:10]:
                        status_icon = "🟢" if span.get("status") == "OK" else "🔴" if span.get("status") == "ERROR" else "⚪"
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.caption(f"{status_icon} {span.get('name', 'unknown')}")
                        with col2:
                            st.caption(f"{span.get('duration_ms', 0):.1f} мс")
                        with col3:
                            st.caption(span.get("start_time", "")[:19])
                else:
                    st.info("Нет трейсов")
            else:
                _show_api_error(resp, prefix="Последние трейсы")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    st.divider()
    st.subheader("Логи приложения")

    with st.container(border=True):
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
            refresh_logs = st.button("Обновить логи", type="primary")

    params = {"limit": limit}
    if since_minutes:
        params["since_minutes"] = since_minutes
    if level_filter:
        params["level"] = level_filter

    if refresh_logs or "logs_cache" not in st.session_state:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/utility/logs",
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                st.session_state.logs_cache = resp.json()
            else:
                _show_api_error(resp, prefix="Логи")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    logs_payload = st.session_state.get("logs_cache", {}) or {}
    logs = logs_payload.get("logs", [])
    stats = logs_payload.get("stats", {})

    if stats:
        with st.container(border=True):
            s_cols = st.columns(5)
            levels = ["total", "DEBUG", "INFO", "WARNING", "ERROR"]
            icons = {"total": "📊", "DEBUG": "🔍", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌"}
            for idx, level in enumerate(levels):
                with s_cols[idx]:
                    st.metric(f"{icons.get(level,'')} {level}", stats.get(level, 0))

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
                c1, c2 = st.columns([1, 5])
                with c1:
                    st.caption(f"{color} {level}")
                    st.caption(timestamp)
                with c2:
                    st.text(message[:200] + ("..." if len(message) > 200 else ""))
                    if logger_name:
                        st.caption(f"Logger: {logger_name}")
    else:
        st.info("Нет логов за выбранный период")

    if st.button("Очистить логи", type="secondary"):
        try:
            resp = requests.post(
                f"{API_BASE_URL}/utility/logs/clear",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                st.success("Логи очищены")
            else:
                _show_api_error(resp, prefix="Очистка логов")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    st.divider()
    st.subheader("Отложенные задачи (Scheduler)")

    with st.container(border=True):
        try:
            stats_resp = requests.get(f"{API_BASE_URL}/scheduler/stats", timeout=10)
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    st.metric("Активен", "Да" if stats.get("scheduler_running") else "Нет")
                with sc2:
                    st.metric("Запланировано", stats.get("total_scheduled_tasks", 0))
                with sc3:
                    st.metric("История задач", stats.get("total_tasks_history", 0))
                if stats.get("tasks_by_status"):
                    with st.expander("По статусам"):
                        st.json(stats.get("tasks_by_status"))
            else:
                _show_api_error(stats_resp, prefix="Статистика задач")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    if "scheduler_tasks" not in st.session_state or st.button("Обновить задачи", type="primary"):
        try:
            resp = requests.get(f"{API_BASE_URL}/scheduler/tasks", timeout=10)
            if resp.status_code == 200:
                st.session_state.scheduler_tasks = resp.json()
            else:
                st.session_state.scheduler_tasks = []
                _show_api_error(resp, prefix="Список задач")
        except Exception as e:
            st.session_state.scheduler_tasks = []
            st.error(f"Ошибка: {e}")

    tasks = st.session_state.get("scheduler_tasks", []) or []
    if not tasks:
        st.info("Нет активных запланированных задач.")
    else:
        for task in tasks:
            task_id = task.get("task_id", "")
            func_name = task.get("func_name", "")
            status = task.get("status", "")
            run_date = task.get("run_date", "")
            metadata = task.get("metadata", {}) if isinstance(task.get("metadata"), dict) else {}
            title = f"{task_id} — {func_name} — {status}"
            with st.expander(title, expanded=False):
                st.write(f"**Run date:** {run_date}")
                if metadata:
                    st.json(metadata)
                if st.button("Отменить задачу", key=f"cancel_{task_id}"):
                    try:
                        resp = requests.delete(
                            f"{API_BASE_URL}/scheduler/task/{task_id}",
                            headers=headers,
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("Задача отменена")
                            st.session_state.scheduler_tasks = [
                                t for t in tasks if t.get("task_id") != task_id
                            ]
                            st.rerun()
                        else:
                            _show_api_error(resp, prefix="Ошибка отмены")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

    st.divider()
    st.subheader("OpenAPI / AsyncAPI")
    col_openapi, col_asyncapi = st.columns(2)
    with col_openapi:
        st.link_button("Swagger UI", f"{API_BASE_URL}/docs")
        st.link_button("openapi.json", f"{API_BASE_URL}/openapi.json")
    with col_asyncapi:
        st.link_button("AsyncAPI HTML", f"{API_BASE_URL}/utility/asyncapi")
        st.link_button("asyncapi.json", f"{API_BASE_URL}/utility/asyncapi.json")

