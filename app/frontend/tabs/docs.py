from __future__ import annotations

import pathlib

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.ui import info_box, section_header


def render(api: ApiClient) -> None:
    st.header("📚 Документация (admin)")

    info_box("Эта вкладка содержит техническую документацию и описание проекта.", emoji="🔒")

    section_header("API Документация", emoji="🔗")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### OpenAPI (REST)")
        st.link_button("📖 Swagger UI", api.origin + "/docs", use_container_width=True)
        st.link_button("📄 OpenAPI JSON", api.origin + "/openapi.json", use_container_width=True)
        st.link_button("📘 ReDoc", api.origin + "/redoc", use_container_width=True)
    with col2:
        st.markdown("### AsyncAPI (Messaging)")
        st.link_button("📖 AsyncAPI HTML", api.url("/utility/asyncapi"), use_container_width=True)
        st.link_button(
            "📄 AsyncAPI JSON",
            api.url("/utility/asyncapi.json"),
            use_container_width=True,
        )

    st.divider()
    section_header("Описание проекта", emoji="📖")

    readme_path = pathlib.Path(__file__).resolve().parents[3] / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
        st.markdown(text)
    except Exception as e:
        st.error(f"❌ Не удалось прочитать README.md: {e}")
        return

    st.divider()
    section_header("Архитектура", emoji="🏗️")

    st.markdown("""
    ### Основные компоненты
    
    1. **FastAPI Backend** (`app/main.py`)
       - REST API для анализа клиентов
       - Интеграция с внешними сервисами
       - Rate limiting и circuit breakers
    
    2. **Streamlit Frontend** (`app/frontend/app.py`)
       - Single-page приложение
       - Ролевой доступ (admin/viewer)
       - Интерактивные дашборды
    
    3. **LangGraph Agents** (`app/agents/`)
       - Оркестратор workflow
       - Поисковые агенты (Perplexity, Tavily)
       - Анализатор рисков
    
    4. **Storage** (`app/storage/`)
       - Tarantool для кэширования
       - In-memory fallback
       - TTL ~ 30 дней для отчётов
    
    5. **External Services**
       - OpenRouter (LLM)
       - Perplexity AI (веб-поиск)
       - Tavily (расширенный поиск)
       - DaData, Casebook, InfoSphere (данные по ИНН)
    """)

    st.divider()
    section_header("Безопасность", emoji="🔐")

    st.markdown("""
    ### Механизмы защиты
    
    - **Admin Token**: Переменная окружения `ADMIN_TOKEN` для доступа к административным функциям
    - **Rate Limiting**: Ограничение запросов по IP (slowapi)
    - **Circuit Breakers**: Защита от каскадных сбоев внешних сервисов
    - **Input Validation**: Pydantic схемы для всех входных данных
    - **CORS**: Настраиваемые политики для фронтенда
    """)

    st.divider()
    section_header("Мониторинг", emoji="📊")

    st.markdown("""
    ### Доступные метрики
    
    - **Health Check**: `/utility/health` (с опцией `deep=true`)
    - **HTTP Metrics**: Статистика запросов, ошибок, таймаутов
    - **Circuit Breakers**: Состояние защитных механизмов
    - **Cache Metrics**: Использование Tarantool/in-memory кэша
    - **Logs & Traces**: Структурированное логирование с фильтрацией
    """)
