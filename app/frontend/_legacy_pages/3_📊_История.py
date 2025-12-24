"""
Страница истории анализов.

Показывает все проведённые анализы с фильтрацией и поиском.
"""

# Для pages/ НЕ нужен set_page_config - Streamlit сам управляет
import os
import sys
from datetime import datetime, timedelta

import streamlit as st

# Add lib to path - ABSOLUTE path to avoid issues
current_file = os.path.abspath(__file__)
pages_dir = os.path.dirname(current_file)
frontend_dir = os.path.dirname(pages_dir)
lib_dir = os.path.join(frontend_dir, "lib")

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from api_client import get_api_client
from components import (
    render_admin_settings,
    render_empty_state,
    render_report_card,
    render_sidebar_auth,
)

# Sidebar (without title - Streamlit adds navigation automatically)
with st.sidebar:
    render_sidebar_auth()
    render_admin_settings()

# Main content
st.title("📊 История анализов")

st.markdown(
    """
Все проведённые анализы контрагентов. Используйте фильтры для быстрого поиска.
"""
)

st.divider()

# ==============================================================================
# FILTERS
# ==============================================================================

with st.container():
    st.subheader("🔍 Фильтры")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        search_query = st.text_input(
            "Поиск",
            placeholder="Название или ИНН",
            help="Поиск по названию компании или ИНН",
        )

    with col2:
        risk_filter = st.selectbox(
            "Уровень риска",
            options=["Все", "low", "medium", "high", "critical"],
            format_func=lambda x: {
                "Все": "Все уровни",
                "low": "🟢 Низкий",
                "medium": "🟡 Средний",
                "high": "🟠 Высокий",
                "critical": "🔴 Критический",
            }.get(x, x),
        )

    with col3:
        date_filter = st.selectbox(
            "Период",
            options=["all", "today", "week", "month"],
            format_func=lambda x: {
                "all": "Всё время",
                "today": "Сегодня",
                "week": "Неделя",
                "month": "Месяц",
            }.get(x, x),
        )

    with col4:
        limit = st.select_slider("На страницу", options=[10, 25, 50, 100], value=50)

st.divider()

# ==============================================================================
# LOAD DATA
# ==============================================================================

client = get_api_client()

# Calculate date range
date_from = None
if date_filter == "today":
    date_from = datetime.now().replace(hour=0, minute=0, second=0)
elif date_filter == "week":
    date_from = datetime.now() - timedelta(days=7)
elif date_filter == "month":
    date_from = datetime.now() - timedelta(days=30)

# Build filters
filters = {
    "limit": limit,
    "offset": st.session_state.get("history_offset", 0),
}

if search_query:
    # Try to detect if it's INN (digits only)
    if search_query.strip().isdigit():
        filters["inn"] = search_query.strip()
    else:
        filters["client_name"] = search_query.strip()

if risk_filter != "Все":
    filters["risk_level"] = risk_filter

if date_from:
    filters["date_from"] = date_from

# Load reports
try:
    with st.spinner("Загрузка..."):
        response = client.list_reports(**filters)

        reports = response.get("reports", [])
        total = response.get("total", 0)
        has_more = response.get("has_more", False)

    # ==============================================================================
    # DISPLAY RESULTS
    # ==============================================================================

    if reports:
        # Stats
        st.caption(f"Найдено: **{total}** анализов")

        st.divider()

        # Reports list
        for idx, report in enumerate(reports):
            render_report_card(report, key_prefix=f"history_{idx}")

            if idx < len(reports) - 1:
                st.divider()

        # Pagination
        st.divider()

        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if st.session_state.get("history_offset", 0) > 0:
                if st.button("⬅️ Предыдущая", use_container_width=True):
                    st.session_state.history_offset = max(
                        0, st.session_state.get("history_offset", 0) - limit
                    )
                    st.rerun()

        with col2:
            current_page = (st.session_state.get("history_offset", 0) // limit) + 1
            total_pages = (total + limit - 1) // limit
            st.caption(f"Страница {current_page} из {total_pages}")

        with col3:
            if has_more:
                if st.button("Следующая ➡️", use_container_width=True):
                    st.session_state.history_offset = (
                        st.session_state.get("history_offset", 0) + limit
                    )
                    st.rerun()

    else:
        render_empty_state(
            icon="📭",
            title="Анализы не найдены",
            description="Попробуйте изменить фильтры или создайте новый анализ",
        )

        if st.button("🎯 Создать анализ", use_container_width=True, type="primary"):
            st.switch_page("pages/1_🎯_Анализ.py")

except Exception as e:
    st.error(f"❌ Ошибка при загрузке истории: {e}")
    st.info("💡 Проверьте, что backend API запущен и доступен")

# ==============================================================================
# BULK ACTIONS (Admin only)
# ==============================================================================

if st.session_state.get("is_admin", False) and reports:
    st.divider()

    with st.expander("⚙️ Массовые операции (Admin)"):
        st.warning("🚨 Действия необратимы!")

        # Select all checkbox
        select_all = st.checkbox("Выбрать все на странице")

        if select_all:
            st.info(f"Выбрано: {len(reports)} отчётов")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("📥 Экспортировать выбранные", use_container_width=True):
                    st.info("Экспорт в разработке...")

            with col2:
                if st.button(
                    "🗑️ Удалить выбранные", use_container_width=True, type="secondary"
                ):
                    confirm = st.checkbox("Подтверждаю удаление")

                    if confirm:
                        try:
                            report_ids = [r["report_id"] for r in reports]
                            result = client.post(
                                "/reports/bulk-delete", json={"report_ids": report_ids}
                            )

                            deleted = result.get("deleted_count", 0)
                            st.success(f"✅ Удалено: {deleted} отчётов")
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ Ошибка удаления: {e}")

# ==============================================================================
# HELP
# ==============================================================================

with st.expander("ℹ️ Справка"):
    st.markdown(
        """
    ### Как пользоваться историей?
    
    **Поиск:**
    - Введите название компании или ИНН в поле поиска
    - Система автоматически определит тип поиска
    
    **Фильтры:**
    - **Уровень риска:** фильтр по оценке риска
    - **Период:** выберите временной диапазон
    - **На страницу:** количество результатов
    
    **Действия с отчётами:**
    - **Просмотреть:** открыть детальный отчёт
    - **Экспорт:** скачать в CSV/JSON
    - **Удалить:** удалить отчёт (только admin)
    
    **Пагинация:**
    - Используйте кнопки "Предыдущая" / "Следующая"
    - Настройте количество результатов на страницу
    
    ---
    
    **Для администраторов:**
    
    Массовые операции позволяют:
    - Экспортировать несколько отчётов сразу
    - Удалить группу отчётов
    """
    )
