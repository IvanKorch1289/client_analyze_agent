"""
Система анализа контрагентов - Главная страница.

Улучшенная версия с:
- Скрытыми техническими элементами
- Безопасной авторизацией
- Улучшенным UX
- Модульной архитектурой
"""

import streamlit as st

# ВАЖНО: set_page_config ДОЛЖЕН быть первой командой Streamlit!
st.set_page_config(
    page_title="Система анализа контрагентов",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Только ПОСЛЕ set_page_config делаем остальные импорты
import os
import sys

# Add lib to path - ABSOLUTE path to avoid issues
current_file = os.path.abspath(__file__)
pages_dir = os.path.dirname(current_file)
frontend_dir = os.path.dirname(pages_dir)
lib_dir = os.path.join(frontend_dir, "lib")

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

# Import our modules (ПОСЛЕ set_page_config!)
from api_client import get_api_client, update_api_client
from components import (
    load_custom_css,
    render_admin_settings,
    render_empty_state,
    render_loading_spinner,
    render_sidebar_auth,
)

# Load custom styles
load_custom_css()

# ==============================================================================
# CUSTOM STYLES
# ==============================================================================

st.markdown("""
<style>
    /* Hide Streamlit branding */
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
    
    /* Sidebar styling */
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
    section[data-testid="stSidebar"] span {
        color: #e5e7eb !important;
    }
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea {
        background-color: #0b1221 !important;
        color: #f9fafb !important;
        border-radius: 6px !important;
        border: 1px solid #1f2937 !important;
    }
    
    /* Button improvements */
    .stButton button {
        border-radius: 0.5rem;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Card styling */
    .card {
        padding: 1.5rem;
        border-radius: 0.75rem;
        background: white;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# STATE INITIALIZATION
# ==============================================================================

def init_session_state():
    """Initialize session state variables."""
    # Load admin token from environment if available
    env_admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    
    defaults = {
        "api_base_url": os.getenv("API_BASE_URL", "http://localhost:8000/api/v1"),
        "admin_token": env_admin_token,  # Load from .env
        "is_admin": False,
        "admin_checked": False,  # Need to check if token is valid
        "last_response": None,
        "selected_report_id": None,
        "show_report_detail": False,
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# Auto-check admin token from .env (if present and not yet checked)
if st.session_state.get("admin_token") and not st.session_state.get("admin_checked"):
    try:
        client = get_api_client()
        response = client.get("/utility/auth/role")
        
        if response.get("is_admin"):
            st.session_state.is_admin = True
        
        st.session_state.admin_checked = True
    except Exception:
        # Silently fail - user can login manually
        st.session_state.admin_checked = True

# ==============================================================================
# SIDEBAR
# ==============================================================================

with st.sidebar:
    # Render authentication
    render_sidebar_auth()
    
    # Render admin settings (only if admin)
    render_admin_settings()

# ==============================================================================
# MAIN CONTENT
# ==============================================================================

st.title("🎯 Система анализа контрагентов")

st.markdown("""
### Добро пожаловать!

Эта система помогает анализировать потенциальных клиентов и контрагентов с использованием:
- 🤖 **AI-анализ** через Perplexity и другие источники
- 📊 **Оценка рисков** с автоматическим формированием отчётов
- 📈 **Аналитика** и статистика по проведённым проверкам
""")

st.divider()

# ==============================================================================
# QUICK ACTIONS
# ==============================================================================

st.subheader("⚡ Быстрые действия")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🎯 Новый анализ", use_container_width=True, type="primary"):
        st.switch_page("pages/1_🎯_Анализ.py")

with col2:
    if st.button("🔍 Поиск по ИНН", use_container_width=True):
        st.switch_page("pages/2_🔍_Поиск.py")

with col3:
    if st.button("📊 История", use_container_width=True):
        st.switch_page("pages/3_📊_История.py")

with col4:
    if st.button("📈 Аналитика", use_container_width=True):
        st.switch_page("pages/4_📈_Аналитика.py")

st.divider()

# ==============================================================================
# RECENT ACTIVITY / DASHBOARD PREVIEW
# ==============================================================================

st.subheader("📋 Последние анализы")

try:
    client = get_api_client()
    
    with st.spinner("Загрузка..."):
        # Get recent reports
        reports_data = client.list_reports(limit=5, offset=0)
        reports = reports_data.get("reports", [])
        
        if reports:
            from components import render_report_card
            
            for idx, report in enumerate(reports):
                render_report_card(report, key_prefix=f"home_{idx}")
                st.divider()
        else:
            render_empty_state(
                icon="📭",
                title="Пока нет анализов",
                description="Начните с создания первого анализа контрагента"
            )

except Exception as e:
    st.error(f"❌ Не удалось загрузить последние анализы: {e}")
    st.info("💡 Проверьте, что backend API запущен и доступен")

# ==============================================================================
# HELP SECTION
# ==============================================================================

with st.expander("ℹ️ Справка"):
    st.markdown("""
    ### Как пользоваться системой?
    
    **1. Анализ контрагента:**
    - Перейдите в раздел "🎯 Анализ"
    - Введите название компании или ИНН
    - Нажмите "Анализировать"
    - Получите детальный отчёт с оценкой рисков
    
    **2. Поиск по внешним источникам:**
    - Используйте раздел "🔍 Поиск"
    - Выберите источник (DaData, Casebook, Perplexity, Tavily)
    - Введите ИНН и параметры поиска
    
    **3. История анализов:**
    - В разделе "📊 История" вы найдёте все проведённые анализы
    - Используйте фильтры для быстрого поиска
    - Экспортируйте отчёты в CSV/JSON
    
    **4. Аналитика:**
    - Раздел "📈 Аналитика" показывает статистику
    - Графики распределения по рискам
    - Тренды и топ компаний
    
    ---
    
    **Для администраторов:**
    
    Войдите с токеном администратора для доступа к:
    - Настройкам API
    - Удалению отчётов
    - Административной панели
    """)

# ==============================================================================
# FOOTER
# ==============================================================================

st.divider()

# Footer
if st.session_state.get("is_admin", False):
    # Admin footer with more info
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.caption("📦 Версия: 1.0.0")
    
    with col2:
        # Link to backend API docs (only for admins)
        api_base_url = st.session_state.get("api_base_url", "http://localhost:8000/api/v1")
        docs_url = f"{api_base_url}/docs"
        st.markdown(f"🔗 [Документация API]({docs_url})")
    
    with col3:
        # Show API status indicator
        try:
            client = get_api_client()
            health = client.health_check()
            
            if health.get("status") == "healthy":
                st.caption("✅ API: Онлайн")
            else:
                st.caption("⚠️ API: Проблемы")
        except:
            st.caption("🔴 API: Офлайн")

else:
    # Simple footer for regular users
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("📦 Версия: 1.0.0")
    
    with col2:
        # Show API status indicator (without link)
        try:
            client = get_api_client()
            health = client.health_check()
            
            if health.get("status") == "healthy":
                st.caption("✅ Система работает")
            else:
                st.caption("⚠️ Возможны проблемы")
        except:
            st.caption("🔴 Система недоступна")
