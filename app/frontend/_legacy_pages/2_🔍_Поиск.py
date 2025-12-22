"""
Страница внешних запросов.

Прямой доступ к внешним API: DaData, Casebook, Perplexity, Tavily.
"""

import streamlit as st

# Для pages/ НЕ нужен set_page_config - Streamlit сам управляет

import os
import sys

# Add lib to path - ABSOLUTE path to avoid issues
current_file = os.path.abspath(__file__)
pages_dir = os.path.dirname(current_file)
frontend_dir = os.path.dirname(pages_dir)
lib_dir = os.path.join(frontend_dir, "lib")

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from api_client import get_api_client
from components import render_admin_settings, render_sidebar_auth

# Sidebar (without title - Streamlit adds navigation automatically)
with st.sidebar:
    render_sidebar_auth()
    render_admin_settings()

# Main content
st.title("🔍 Внешние источники данных")

st.markdown("""
Прямой доступ к внешним API для получения данных о компаниях.
Полезно для быстрой проверки конкретных источников.
""")

st.divider()

# ==============================================================================
# SOURCE SELECTION
# ==============================================================================

source = st.radio(
    "Выберите источник",
    options=["dadata", "casebook", "infosphere", "perplexity", "tavily"],
    format_func=lambda x: {
        "dadata": "📊 DaData (базовая информация о компании)",
        "casebook": "⚖️ Casebook (судебные дела)",
        "infosphere": "🌐 InfoSphere (дополнительная аналитика)",
        "perplexity": "🤖 Perplexity AI (поиск и аналитика)",
        "tavily": "🔍 Tavily (веб-поиск)",
    }.get(x, x),
    horizontal=False
)

st.divider()

client = get_api_client()

# ==============================================================================
# FORMS FOR EACH SOURCE
# ==============================================================================

if source in ["dadata", "casebook", "infosphere"]:
    # INN-based sources
    st.subheader(f"Запрос к {source.upper()}")
    
    with st.form(f"{source}_form"):
        inn = st.text_input(
            "ИНН компании",
            placeholder="Введите 10 или 12 цифр",
            help="ИНН должен содержать 10 цифр (юр. лицо) или 12 цифр (ИП)",
            max_chars=12
        )
        
        submitted = st.form_submit_button("🔍 Получить данные", use_container_width=True, type="primary")
    
    if submitted and inn:
        # Validate INN
        if not inn.isdigit() or len(inn) not in (10, 12):
            st.error("❌ ИНН должен содержать 10 или 12 цифр")
            st.stop()
        
        with st.spinner(f"Запрос к {source}..."):
            try:
                # Make request
                endpoint = f"/data/client/{source}/{inn}"
                response = client.get(endpoint)
                
                st.success("✅ Данные получены")
                
                # Display response
                st.json(response)
                
                # Download button
                import json
                json_str = json.dumps(response, ensure_ascii=False, indent=2)
                
                st.download_button(
                    label="📥 Скачать JSON",
                    data=json_str,
                    file_name=f"{source}_{inn}.json",
                    mime="application/json",
                )
            
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

elif source == "perplexity":
    # Perplexity AI search
    st.subheader("🤖 Perplexity AI")
    
    st.caption("AI-powered поиск информации о компании. Возвращает структурированный ответ с цитатами.")
    
    with st.form("perplexity_form"):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            inn = st.text_input(
                "ИНН компании",
                placeholder="7707083893",
                max_chars=12
            )
        
        with col2:
            search_query = st.text_input(
                "Что искать",
                placeholder="судебные дела, банкротство, новости",
                help="Опишите, какую информацию вы ищете"
            )
        
        recency = st.selectbox(
            "Актуальность",
            options=["month", "week", "day"],
            format_func=lambda x: {"month": "За месяц", "week": "За неделю", "day": "За день"}.get(x, x)
        )
        
        submitted = st.form_submit_button("🔍 Поиск", use_container_width=True, type="primary")
    
    if submitted and inn and search_query:
        # Validate INN
        if not inn.isdigit() or len(inn) not in (10, 12):
            st.error("❌ ИНН должен содержать 10 или 12 цифр")
            st.stop()
        
        with st.spinner("🤖 Perplexity AI думает..."):
            try:
                result = client.search_perplexity(inn, search_query)
                
                if result.get("status") == "success":
                    st.success("✅ Поиск завершён")
                    
                    # Display answer
                    st.markdown("### 📝 Ответ:")
                    st.markdown(result.get("content", "Нет содержимого"))
                    
                    # Citations
                    citations = result.get("citations", [])
                    if citations:
                        with st.expander("📚 Источники"):
                            for cite in citations:
                                st.caption(f"• {cite}")
                else:
                    st.error(result.get("message", "Ошибка поиска"))
            
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

elif source == "tavily":
    # Tavily search
    st.subheader("🔍 Tavily")
    
    st.caption("Веб-поиск с глубоким анализом. Возвращает релевантные результаты с ответом AI.")
    
    with st.form("tavily_form"):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            inn = st.text_input(
                "ИНН компании",
                placeholder="7707083893",
                max_chars=12
            )
        
        with col2:
            search_query = st.text_input(
                "Что искать",
                placeholder="финансовое состояние, репутация",
                help="Опишите, какую информацию вы ищете"
            )
        
        col1, col2 = st.columns(2)
        
        with col1:
            max_results = st.slider("Максимум результатов", 1, 10, 5)
        
        with col2:
            search_depth = st.selectbox(
                "Глубина поиска",
                options=["basic", "advanced"],
                format_func=lambda x: {"basic": "Базовый", "advanced": "Расширенный"}.get(x, x)
            )
        
        submitted = st.form_submit_button("🔍 Поиск", use_container_width=True, type="primary")
    
    if submitted and inn and search_query:
        # Validate INN
        if not inn.isdigit() or len(inn) not in (10, 12):
            st.error("❌ ИНН должен содержать 10 или 12 цифр")
            st.stop()
        
        with st.spinner("🔍 Tavily ищет..."):
            try:
                result = client.search_tavily(inn, search_query, max_results=max_results)
                
                if result.get("status") == "success":
                    st.success("✅ Поиск завершён")
                    
                    # AI Answer
                    answer = result.get("answer", "")
                    if answer:
                        st.markdown("### 🤖 Ответ AI:")
                        st.markdown(answer)
                        st.divider()
                    
                    # Results
                    st.markdown("### 📋 Результаты:")
                    
                    results = result.get("results", [])
                    if results:
                        for idx, item in enumerate(results, 1):
                            with st.expander(f"**{idx}. {item.get('title', 'Без заголовка')}**"):
                                content = item.get("content", "") or item.get("snippet", "")
                                st.markdown(content)
                                
                                url = item.get("url", "")
                                if url:
                                    st.caption(f"🔗 [{url}]({url})")
                    else:
                        st.info("Нет результатов")
                else:
                    st.error(result.get("message", "Ошибка поиска"))
            
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")

# ==============================================================================
# HELP
# ==============================================================================

with st.expander("ℹ️ Справка по источникам"):
    st.markdown("""
    ### Описание источников:
    
    **📊 DaData:**
    - Базовая информация о компании (название, адрес, ОКВЭД)
    - Данные о руководителе
    - Статус компании (активна/ликвидирована)
    - Финансовая информация
    
    **⚖️ Casebook:**
    - Судебные дела компании
    - История арбитражных разбирательств
    - Исполнительные производства
    
    **🌐 InfoSphere:**
    - Дополнительная аналитика
    - Связи с другими компаниями
    - Расширенная информация
    
    **🤖 Perplexity AI:**
    - AI-поиск с анализом
    - Структурированный ответ на ваш запрос
    - Цитаты источников
    - Фильтр по актуальности (день/неделя/месяц)
    
    **🔍 Tavily:**
    - Глубокий веб-поиск
    - AI-ответ на основе найденного
    - Релевантные результаты с контентом
    - Настройка глубины поиска
    
    ---
    
    **Советы:**
    
    - Для быстрой проверки используйте DaData
    - Для проверки судебной истории - Casebook
    - Для AI-анализа и новостей - Perplexity
    - Для глубокого поиска - Tavily
    """)
