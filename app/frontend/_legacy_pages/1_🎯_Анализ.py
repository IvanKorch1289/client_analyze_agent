"""
Страница анализа контрагентов.

Позволяет отправить запрос агенту для анализа компании.
"""

# ВАЖНО: set_page_config ПЕРВЫМ (если нужен)
# Для pages/ в multi-page app обычно НЕ нужен - Streamlit сам управляет
# st.set_page_config(...)  # Закомментировано - не нужно для pages/
import os
import sys

import streamlit as st

# Add lib to path - ABSOLUTE path to avoid issues
current_file = os.path.abspath(__file__)
pages_dir = os.path.dirname(current_file)
frontend_dir = os.path.dirname(pages_dir)
lib_dir = os.path.join(frontend_dir, "lib")

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from api_client import get_api_client
from components import render_admin_settings, render_risk_badge, render_sidebar_auth

# Sidebar (without title - Streamlit adds navigation automatically)
with st.sidebar:
    render_sidebar_auth()
    render_admin_settings()

# Main content
st.title("🎯 Анализ контрагентов")

st.markdown(
    """
Введите название компании или ИНН для проведения комплексного анализа.
Система проверит компанию по множеству источников и оценит уровень риска.
"""
)

st.divider()

# ==============================================================================
# ANALYSIS FORM
# ==============================================================================

with st.form("analysis_form"):
    st.subheader("📝 Введите данные для анализа")

    col1, col2 = st.columns([2, 1])

    with col1:
        query = st.text_area(
            "Запрос агенту",
            height=150,
            placeholder="Например: Проанализируй компанию Газпром с ИНН 7707083893",
            help="Введите название компании или ИНН. Агент автоматически извлечёт нужную информацию.",
        )

    with col2:
        st.caption("💡 **Примеры запросов:**")
        st.caption("• Проверить ООО 'Ромашка'")
        st.caption("• Анализ по ИНН 7707083893")
        st.caption("• Оценить риски Газпром")

        st.markdown("")
        st.markdown("")

        if st.form_submit_button(
            "🚀 Анализировать", use_container_width=True, type="primary"
        ):
            submitted = True
        else:
            submitted = False

# ==============================================================================
# PROCESS ANALYSIS
# ==============================================================================

if submitted and query.strip():
    client = get_api_client()

    with st.spinner("🔍 Агенты работают... Это может занять 1-2 минуты."):
        try:
            # Send prompt to agent
            result = client.send_prompt(query.strip())

            # Save to session state
            st.session_state.last_response = result
            st.session_state.last_thread_id = result.get("thread_id")

            st.success("✅ Анализ завершён!")

        except Exception as e:
            st.error(f"❌ Ошибка при анализе: {e}")
            st.info("💡 Проверьте, что backend API запущен и доступен")
            st.stop()

# ==============================================================================
# DISPLAY RESULTS
# ==============================================================================

if st.session_state.get("last_response"):
    result = st.session_state.last_response

    st.divider()
    st.subheader("📊 Результат анализа")

    # Metadata
    col1, col2, col3 = st.columns(3)

    with col1:
        thread_id = result.get("thread_id", "Н/Д")
        st.metric("Thread ID", thread_id)

    with col2:
        tools_used = "Да" if result.get("tools_used") else "Нет"
        st.metric("Инструменты", tools_used)

    with col3:
        timestamp = result.get("timestamp", "Н/Д")
        st.metric(
            "Время", timestamp[:19] if timestamp and len(timestamp) > 19 else timestamp
        )

    st.divider()

    # Response content
    st.markdown("### 📄 Отчёт")

    response_text = result.get("response", "Нет ответа")
    st.markdown(response_text)

    # Raw result (expandable)
    with st.expander("🔍 Детальная информация"):
        raw_result = result.get("raw_result", {})

        if raw_result:
            # Extract report data if available
            report = raw_result.get("report", {})

            if report:
                risk_assessment = report.get("risk_assessment", {})

                # Risk info
                if risk_assessment:
                    st.markdown("#### ⚠️ Оценка рисков")

                    col1, col2 = st.columns(2)

                    with col1:
                        risk_level = risk_assessment.get("level", "unknown")
                        risk_score = risk_assessment.get("score", 0)

                        st.markdown(
                            render_risk_badge(risk_level, risk_score),
                            unsafe_allow_html=True,
                        )

                    with col2:
                        st.metric("Балл риска", f"{risk_score}/100")

                    # Risk factors
                    factors = risk_assessment.get("factors", [])
                    if factors:
                        st.markdown("**Факторы риска:**")
                        for factor in factors:
                            st.markdown(f"• {factor}")

                # Findings
                findings = report.get("findings", [])
                if findings:
                    st.markdown("#### 📋 Находки")
                    for finding in findings:
                        with st.expander(f"**{finding.get('category', 'Категория')}**"):
                            st.markdown(
                                f"**Sentiment:** {finding.get('sentiment', 'neutral')}"
                            )
                            st.markdown(finding.get("key_points", ""))

                # Recommendations
                recommendations = report.get("recommendations", [])
                if recommendations:
                    st.markdown("#### 💡 Рекомендации")
                    for idx, rec in enumerate(recommendations, 1):
                        st.markdown(f"{idx}. {rec}")

        # Full JSON
        st.json(raw_result)

    # Actions
    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📥 Скачать отчёт", use_container_width=True):
            # Download as text
            st.download_button(
                label="Скачать как TXT",
                data=response_text,
                file_name=f"report_{result.get('thread_id', 'unknown')}.txt",
                mime="text/plain",
            )

    with col2:
        if st.button("🔄 Новый анализ", use_container_width=True):
            st.session_state.last_response = None
            st.rerun()

    with col3:
        if st.button("📊 В историю", use_container_width=True):
            st.switch_page("pages/3_📊_История.py")

    with col4:
        if st.button("🏠 На главную", use_container_width=True):
            st.switch_page("app.py")

elif submitted:
    st.warning("⚠️ Введите запрос для анализа")

# ==============================================================================
# HELP
# ==============================================================================

if not st.session_state.get("last_response"):
    with st.expander("ℹ️ Как работает анализ?"):
        st.markdown(
            """
        ### Процесс анализа:
        
        1. **Извлечение данных:**
           - Агент автоматически извлекает ИНН и название компании из вашего запроса
           - Если ИНН не указан, поиск идёт по названию
        
        2. **Сбор информации:**
           - Запрос в DaData (базовая информация о компании)
           - Поиск в Casebook (судебные дела)
           - Поиск через Perplexity AI (новости, репутация)
           - Дополнительные источники
        
        3. **Анализ рисков:**
           - AI-агент анализирует собранные данные
           - Оценивает риски по шкале 0-100
           - Выявляет факторы риска
           - Формирует рекомендации
        
        4. **Формирование отчёта:**
           - Структурированный отчёт с оценкой
           - Детальные находки по категориям
           - Рекомендации по работе с контрагентом
        
        ---
        
        **Время анализа:** обычно 1-2 минуты
        
        **Источники:** DaData, Casebook, Perplexity AI, Tavily
        """
        )
