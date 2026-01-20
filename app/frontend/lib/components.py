"""
Переиспользуемые UI компоненты для фронтенда.

Provides common UI elements:
- Sidebar navigation
- Authentication components
- Metric cards
- Risk indicators
- Data tables
"""

import os
from typing import Any, Dict, Optional

import streamlit as st

# Avoid circular imports - import inside functions when needed


def load_custom_css():
    """Load custom CSS styles from assets/styles.css."""
    try:
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "styles.css"
        )

        if os.path.exists(css_path):
            with open(css_path) as f:
                st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        # Silently fail if CSS not found
        pass


def render_sidebar_auth():
    """
    Render authentication section in sidebar.

    Shows login form for non-authenticated users and logout for admins.
    """
    # Lazy import to avoid circular dependency
    from api_client import get_api_client, update_api_client

    st.sidebar.divider()

    if not st.session_state.get("is_admin", False):
        # Login form (collapsed by default - security)
        with st.sidebar.expander("🔐 Вход для администратора", expanded=False):
            st.caption("Для доступа к расширенным функциям")

            token = st.text_input(
                "Токен администратора",
                type="password",
                key="admin_token_input",
                label_visibility="collapsed",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔓 Войти", use_container_width=True, key="btn_login"):
                    if token:
                        # Check token - создаём НОВЫЙ клиент с этим токеном
                        try:
                            from api_client import APIClient

                            # Создаём новый клиент с введённым токеном
                            base_url = st.session_state.get(
                                "api_base_url", "http://localhost:8000/api/v1"
                            )
                            test_client = APIClient(base_url, token)

                            response = test_client.get("/utility/auth/role")

                            # Проверяем ответ
                            role = response.get("role", "")
                            is_admin = response.get("is_admin", False)

                            if role == "admin" or is_admin == True:
                                # Успешный вход - сохраняем состояние и делаем rerun БЕЗ показа ошибок
                                st.session_state.admin_token = token
                                st.session_state.is_admin = True
                                st.session_state.admin_checked = True
                                st.session_state.login_error = None  # Очищаем ошибку
                                update_api_client()
                                # НЕ показываем success - просто rerun
                                st.rerun()
                            else:
                                # Сохраняем ошибку в session_state
                                st.session_state.login_error = "invalid_token"

                        except Exception as e:
                            # Сохраняем ошибку подключения
                            st.session_state.login_error = "connection_error"
                    else:
                        st.session_state.login_error = "empty_token"

            # Показываем ошибки ПОСЛЕ кнопки (не будут сохраняться после rerun)
            if "login_error" in st.session_state and st.session_state.login_error:
                error_type = st.session_state.login_error

                if error_type == "invalid_token":
                    st.error("❌ Неверный токен")
                elif error_type == "connection_error":
                    st.error("❌ Ошибка подключения")
                elif error_type == "empty_token":
                    st.warning("⚠️ Введите токен")

            with col2:
                if st.button("ℹ️ Помощь", use_container_width=True):
                    st.info("Токен находится в переменной окружения ADMIN_TOKEN")

    else:
        # Show admin status
        st.sidebar.success("✅ Администратор")

        if st.sidebar.button("🚪 Выйти", use_container_width=True):
            st.session_state.admin_token = ""
            st.session_state.is_admin = False
            update_api_client()
            st.rerun()


def render_admin_settings():
    """
    Render admin settings panel (only for admins).

    Shows:
    - API Base URL configuration
    - API health check
    - System settings
    """
    # Lazy import to avoid circular dependency
    from api_client import get_api_client, update_api_client

    if not st.session_state.get("is_admin", False):
        return

    st.sidebar.divider()
    st.sidebar.subheader("⚙️ Настройки администратора")

    # API URL configuration
    current_url = st.session_state.get("api_base_url", "http://localhost:8000/api/v1")

    api_url = st.sidebar.text_input(
        "API Base URL", value=current_url, help="URL бэкенда API", key="api_url_input"
    )

    if api_url != current_url:
        st.session_state.api_base_url = api_url
        update_api_client()
        st.sidebar.info("🔄 URL обновлён")

    # Health check
    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("🔍 Проверить API", use_container_width=True):
            try:
                client = get_api_client()
                health = client.health_check()

                status = health.get("status", "unknown")
                if status == "healthy":
                    st.sidebar.success(f"✅ API работает: {status}")
                else:
                    st.sidebar.warning(f"⚠️ API статус: {status}")

                    issues = health.get("issues", [])
                    if issues:
                        with st.sidebar.expander("Проблемы"):
                            for issue in issues[:5]:
                                st.caption(f"• {issue}")

            except Exception as e:
                st.sidebar.error(f"❌ API недоступен: {e}")

    with col2:
        if st.button("📊 Метрики", use_container_width=True):
            st.session_state.show_metrics_modal = True


def render_risk_badge(risk_level: str, risk_score: int) -> str:
    """
    Render risk level badge with color.

    Args:
        risk_level: Risk level (low, medium, high, critical)
        risk_score: Risk score (0-100)

    Returns:
        HTML string with styled badge
    """
    colors = {
        "low": ("#10b981", "#d1fae5"),
        "medium": ("#f59e0b", "#fef3c7"),
        "high": ("#ef4444", "#fee2e2"),
        "critical": ("#dc2626", "#fecaca"),
        "unknown": ("#6b7280", "#f3f4f6"),
    }

    color, bg_color = colors.get(risk_level.lower(), colors["unknown"])

    labels = {
        "low": "Низкий",
        "medium": "Средний",
        "high": "Высокий",
        "critical": "Критический",
        "unknown": "Неизвестно",
    }

    label = labels.get(risk_level.lower(), risk_level)

    return f"""
    <span style="
        background-color: {bg_color};
        color: {color};
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.875rem;
        display: inline-block;
    ">
        {label} ({risk_score})
    </span>
    """


def render_metric_card(
    label: str, value: str, delta: Optional[str] = None, icon: str = "📊"
):
    """
    Render metric card.

    Args:
        label: Metric label
        value: Metric value
        delta: Optional delta/change indicator
        icon: Optional emoji icon
    """
    delta_html = ""
    if delta:
        delta_color = "green" if not delta.startswith("-") else "red"
        delta_html = f'<div style="font-size: 0.875rem; color: {delta_color}; margin-top: 0.25rem;">{delta}</div>'

    st.markdown(
        f"""
    <div style="
        padding: 1.5rem;
        border-radius: 0.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    ">
        <div style="font-size: 0.875rem; opacity: 0.9; margin-bottom: 0.5rem;">
            {icon} {label}
        </div>
        <div style="font-size: 2rem; font-weight: bold; line-height: 1;">
            {value}
        </div>
        {delta_html}
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_report_card(report: Dict[str, Any], key_prefix: str = ""):
    """
    Render report card with summary.

    Args:
        report: Report dictionary
        key_prefix: Prefix for button keys
    """
    risk_badge = render_risk_badge(
        report.get("risk_level", "unknown"), report.get("risk_score", 0)
    )

    with st.container():
        col1, col2, col3 = st.columns([3, 2, 2])

        with col1:
            st.markdown(f"**{report.get('client_name', 'Н/Д')}**")
            st.caption(f"ИНН: {report.get('inn', 'Н/Д')}")

        with col2:
            st.markdown(risk_badge, unsafe_allow_html=True)

        with col3:
            from datetime import datetime

            created_at = report.get("created_at", 0)
            if created_at:
                date_str = datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M")
                st.caption(f"📅 {date_str}")

        # Action buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "👁️ Просмотреть",
                key=f"{key_prefix}_view_{report.get('report_id')}",
                use_container_width=True,
            ):
                st.session_state.selected_report_id = report.get("report_id")
                st.session_state.show_report_detail = True

        with col2:
            if st.button(
                "📥 Экспорт",
                key=f"{key_prefix}_export_{report.get('report_id')}",
                use_container_width=True,
            ):
                # Export logic
                pass

        with col3:
            if st.session_state.get("is_admin", False):
                if st.button(
                    "🗑️ Удалить",
                    key=f"{key_prefix}_delete_{report.get('report_id')}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state.delete_report_id = report.get("report_id")


def render_loading_spinner(text: str = "Загрузка..."):
    """
    Render loading spinner with text.

    Args:
        text: Loading text
    """
    st.markdown(
        f"""
    <div style="text-align: center; padding: 3rem;">
        <div style="font-size: 3rem; animation: spin 1s linear infinite;">⏳</div>
        <div style="margin-top: 1rem; color: #6b7280;">{text}</div>
    </div>
    
    <style>
    @keyframes spin {{
        from {{ transform: rotate(0deg); }}
        to {{ transform: rotate(360deg); }}
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_empty_state(
    icon: str = "📭", title: str = "Нет данных", description: str = ""
):
    """
    Render empty state placeholder.

    Args:
        icon: Emoji icon
        title: Title text
        description: Optional description
    """
    st.markdown(
        f"""
    <div style="
        text-align: center;
        padding: 4rem 2rem;
        color: #6b7280;
    ">
        <div style="font-size: 4rem; margin-bottom: 1rem;">{icon}</div>
        <div style="font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem;">
            {title}
        </div>
        {f'<div style="font-size: 0.875rem;">{description}</div>' if description else ''}
    </div>
    """,
        unsafe_allow_html=True,
    )


__all__ = [
    "load_custom_css",
    "render_sidebar_auth",
    "render_admin_settings",
    "render_risk_badge",
    "render_metric_card",
    "render_report_card",
    "render_loading_spinner",
    "render_empty_state",
]
