import requests
import streamlit as st

st.set_page_config(page_title="Multi-Agent System", layout="wide")
st.title("🤖 Multi-Agent System Console")

# ========================
# Боковая панель навигации
# ========================
st.sidebar.title("Навигация")
page = st.sidebar.radio(
    "Выберите раздел", ["Запрос агенту", "История", "Внешние данные", "Утилиты"]
)

# ========================
# Инициализация состояния
# ========================
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# ========================
# Страница: Запрос агенту
# ========================
if page == "Запрос агенту":
    st.header("Отправить запрос агенту")
    query = st.text_area("Введите запрос:", height=100)
    if st.button("Отправить"):
        with st.spinner("Обработка..."):
            try:
                response = requests.post(
                    "http://localhost:8000/ask", data={"user_input": query}
                )
                if response.status_code == 200:
                    st.session_state.last_response = response.text
                    st.session_state.session_id = "temp_session"  # Для демо
                    st.rerun()
                else:
                    st.error(f"Ошибка: {response.status_code}")
            except Exception as e:
                st.error(f"Ошибка подключения: {e}")

    if st.session_state.last_response:
        st.components.v1.html(
            st.session_state.last_response, height=400, scrolling=True
        )

        st.subheader("Отправить фидбек")
        correct = st.radio("Правильно?", ("Да", "Нет"), index=0)
        feedback = st.text_area("Комментарий") if correct == "Нет" else ""
        if st.button("Отправить фидбек"):
            try:
                resp = requests.post(
                    f"http://localhost:8000/confirm/{st.session_state.session_id}",
                    data={
                        "correct": "true" if correct == "Да" else "false",
                        "feedback": feedback,
                    },
                )
                if resp.status_code == 200:
                    st.success("Фидбек отправлен!")
                    st.session_state.last_response = None
                else:
                    st.error("Ошибка отправки")
            except Exception as e:
                st.error(f"Ошибка: {e}")

# ========================
# Страница: История
# ========================
elif page == "История":
    st.header("История запросов")

    if st.button("Обновить список"):
        try:
            resp = requests.get("http://localhost:8000/history")
            if resp.status_code == 200:
                st.components.v1.html(resp.text, height=600, scrolling=True)
            else:
                st.error("Ошибка загрузки истории")
        except Exception as e:
            st.error(f"Ошибка: {e}")

# ========================
# Страница: Внешние данные
# ========================
elif page == "Внешние данные":
    st.header("Запросы к внешним источникам")
    inn = st.text_input("ИНН", value="7707083893")
    source = st.selectbox("Источник", ["info", "dadata", "casebook", "infosphere"])

    if st.button("Получить данные"):
        with st.spinner("Запрос..."):
            try:
                url = f"http://localhost:8000/data/client/{source}/{inn}"
                resp = requests.get(url)
                if resp.status_code == 200:
                    st.json(resp.json())
                else:
                    st.error(f"Ошибка: {resp.status_code}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

# ========================
# Страница: Утилиты
# ========================
elif page == "Утилиты":
    st.header("Служебные функции")

    st.subheader("Очистка кэша Tarantool")
    confirm = st.checkbox("Подтвердить очистку")
    if st.button("Инвалидировать кэш"):
        try:
            url = f"http://localhost:8000/utility/validate_cache?confirm={'true' if confirm else 'false'}"
            resp = requests.get(url)
            if resp.status_code == 200:
                st.success(resp.json().get("message", "Выполнено"))
            else:
                st.error(f"Ошибка: {resp.status_code}")
        except Exception as e:
            st.error(f"Ошибка: {e}")

    st.subheader("Список тредов")
    if st.button("Получить список тредов"):
        try:
            resp = requests.get("http://localhost:8000/agent/threads")
            if resp.status_code == 200:
                st.json(resp.json())
            else:
                st.error(f"Ошибка: {resp.status_code}")
        except Exception as e:
            st.error(f"Ошибка: {e}")
