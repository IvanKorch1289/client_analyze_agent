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
    key="nav_radio"
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
# Страница: Утилиты
# ========================
elif page == "Утилиты":
    st.header("⚙️ Служебные функции")

    # Очистка кэша
    st.subheader("🧹 Очистка кэша Tarantool")
    confirm = st.checkbox("⚠️ Подтверждаю очистку кэша", value=False)
    if st.button("💥 Инвалидировать кэш", type="primary", disabled=not confirm):
        try:
            url = f"{API_BASE_URL}/utility/validate_cache?confirm=true"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                st.success("✅ Кэш успешно очищен!")
                st.json(resp.json())
            else:
                st.error(f"Ошибка: {resp.status_code} - {resp.text}")
        except Exception as e:
            st.error(f"❌ Ошибка: {e}")

    st.divider()

    # Статус системы
    st.subheader("📊 Статус системы")
    col1, col2 = st.columns(2)

    with col1:
        try:
            resp = requests.get(f"{API_BASE_URL}/agent/threads", timeout=5)
            if resp.status_code == 200:
                count = resp.json().get("total", 0)
                st.metric("Всего тредов", count)
            else:
                st.error("Не удалось получить статус")
        except Exception:
            st.error("Tarantool недоступен")

    with col2:
        try:
            resp = requests.get(f"{API_BASE_URL}/docs", timeout=5)
            if resp.status_code == 200:
                st.success("FastAPI ✅")
            else:
                st.error("FastAPI ❌")
        except Exception:
            st.error("FastAPI ❌")

    st.divider()

    # Тест подключения
    if st.button("🔌 Проверить подключение к FastAPI"):
        try:
            resp = requests.get(f"{API_BASE_URL}/agent/threads", timeout=5)
            st.success(f"✅ Подключение успешно! Статус: {resp.status_code}")
        except Exception as e:
            st.error(f"❌ Ошибка подключения: {e}")
