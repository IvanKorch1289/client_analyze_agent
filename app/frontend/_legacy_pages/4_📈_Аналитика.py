"""
Страница аналитики и статистики.

Dashboard с ключевыми метриками, графиками и трендами.
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
from components import (
    render_admin_settings,
    render_empty_state,
    render_metric_card,
    render_sidebar_auth,
)

# Sidebar (without title - Streamlit adds navigation automatically)
with st.sidebar:
    render_sidebar_auth()
    render_admin_settings()

# Main content
st.title("📈 Аналитика и статистика")

st.markdown("""
Обзор всех проведённых анализов с ключевыми метриками и трендами.
""")

st.divider()

# ==============================================================================
# LOAD DASHBOARD DATA
# ==============================================================================

client = get_api_client()

try:
    with st.spinner("Загрузка аналитики..."):
        dashboard_data = client.get_dashboard_analytics()
    
    data = dashboard_data.get("data", {})
    
    # ==============================================================================
    # KEY METRICS
    # ==============================================================================
    
    st.subheader("📊 Ключевые метрики")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total = data.get("total_analyses", 0)
        render_metric_card("Всего анализов", str(total), icon="📊")
    
    with col2:
        today = data.get("today_analyses", 0)
        render_metric_card("Сегодня", str(today), icon="📅")
    
    with col3:
        avg_risk = data.get("avg_risk_score", 0)
        render_metric_card("Средний риск", f"{avg_risk:.1f}", icon="⚠️")
    
    with col4:
        high_risk = data.get("high_risk_count", 0)
        render_metric_card("Высокий риск", str(high_risk), icon="🔴")
    
    st.divider()
    
    # ==============================================================================
    # RISK DISTRIBUTION
    # ==============================================================================
    
    st.subheader("📊 Распределение по рискам")
    
    risk_dist = data.get("risk_distribution", {})
    
    if risk_dist and sum(risk_dist.values()) > 0:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Bar chart using streamlit built-in
            import pandas as pd
            
            risk_labels = {
                "low": "🟢 Низкий",
                "medium": "🟡 Средний",
                "high": "🟠 Высокий",
                "critical": "🔴 Критический"
            }
            
            # Prepare data
            chart_data = {}
            for level in ["low", "medium", "high", "critical"]:
                count = risk_dist.get(level, 0)
                if count > 0:
                    chart_data[risk_labels[level]] = count
            
            if chart_data:
                df = pd.DataFrame.from_dict(chart_data, orient='index', columns=['Количество'])
                st.bar_chart(df, height=300, use_container_width=True)
        
        with col2:
            st.markdown("#### Детали:")
            
            for level, count in risk_dist.items():
                icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(level, "⚪")
                label = risk_labels.get(level, level)
                st.metric(f"{icon} {label}", count)
    
    else:
        render_empty_state(
            icon="📊",
            title="Нет данных для отображения",
            description="Создайте первый анализ для просмотра статистики"
        )
    
    st.divider()
    
    # ==============================================================================
    # TIMELINE CHART
    # ==============================================================================
    
    st.subheader("📈 Анализы за последние 7 дней")
    
    timeline = data.get("timeline_7d", [])
    
    if timeline:
        import pandas as pd
        
        # Prepare data for charts
        dates = [item["date"] for item in timeline]
        counts = [item["count"] for item in timeline]
        avg_risks = [item.get("avg_risk", 0) for item in timeline]
        
        # Create DataFrame
        df = pd.DataFrame({
            "Дата": dates,
            "Количество анализов": counts,
            "Средний риск": avg_risks
        })
        df = df.set_index("Дата")
        
        # Display charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Количество анализов**")
            st.bar_chart(df["Количество анализов"], height=300)
        
        with col2:
            st.markdown("**Средний балл риска**")
            st.line_chart(df["Средний риск"], height=300)
    
    st.divider()
    
    # ==============================================================================
    # SERVICES STATUS
    # ==============================================================================
    
    st.subheader("🔧 Статус сервисов")
    
    services = data.get("services_status", {})
    
    if services:
        col1, col2, col3 = st.columns(3)
        
        for idx, (service_key, service_info) in enumerate(services.items()):
            col = [col1, col2, col3][idx % 3]
            
            with col:
                configured = service_info.get("configured", False)
                name = service_info.get("name", service_key)
                
                if configured:
                    st.success(f"✅ {name}")
                else:
                    st.warning(f"⚠️ {name} (не настроен)")
    
    st.divider()
    
    # ==============================================================================
    # CACHE STATUS
    # ==============================================================================
    
    cache_info = data.get("cache", {})
    
    if cache_info:
        st.subheader("💾 Кэш")
        
        col1, col2 = st.columns(2)
        
        with col1:
            hit_rate = cache_info.get("hit_rate", 0)
            st.metric("Hit Rate", f"{hit_rate:.1f}%")
        
        with col2:
            size = cache_info.get("size", 0)
            st.metric("Размер", f"{size} записей")

except Exception as e:
    st.error(f"❌ Ошибка при загрузке аналитики: {e}")
    st.info("💡 Проверьте, что backend API запущен и доступен")

# ==============================================================================
# TRENDS (Optional - expandable)
# ==============================================================================

with st.expander("📊 Расширенная аналитика"):
    st.subheader("Тренды за последние 30 дней")
    
    try:
        trends_data = client.get_risk_trends(days=30)
        trends = trends_data.get("trends", {})
        
        trend_direction = trends.get("trend_direction", "stable")
        avg_change = trends.get("avg_change_percent", 0)
        
        if trend_direction == "up":
            st.warning(f"⬆️ Риски растут: +{avg_change:.1f}%")
        elif trend_direction == "down":
            st.success(f"⬇️ Риски снижаются: {avg_change:.1f}%")
        else:
            st.info("➡️ Риски стабильны")
        
        # Timeline
        timeline_30d = trends.get("timeline", [])
        
        if timeline_30d:
            import pandas as pd
            
            dates = [item["date"] for item in timeline_30d]
            avg_risks = [item.get("avg_risk", 0) for item in timeline_30d]
            
            # Create DataFrame
            df = pd.DataFrame({
                "Дата": dates,
                "Средний риск": avg_risks
            })
            df = df.set_index("Дата")
            
            st.line_chart(df, height=400)
    
    except Exception as e:
        st.error(f"Ошибка загрузки трендов: {e}")

# ==============================================================================
# HELP
# ==============================================================================

with st.expander("ℹ️ Справка"):
    st.markdown("""
    ### О метриках:
    
    **Всего анализов:**
    - Общее количество проведённых анализов контрагентов
    
    **Сегодня:**
    - Количество анализов за текущие сутки
    
    **Средний риск:**
    - Средний балл риска по всем анализам (0-100)
    
    **Высокий риск:**
    - Количество компаний с высоким (50-74) или критическим (75-100) риском
    
    ---
    
    **Распределение по рискам:**
    - 🟢 **Низкий (0-24):** Стандартная процедура
    - 🟡 **Средний (25-49):** Дополнительная проверка
    - 🟠 **Высокий (50-74):** Глубокое расследование
    - 🔴 **Критический (75-100):** Рекомендуется отказ
    
    ---
    
    **График анализов:**
    - Показывает количество анализов по дням
    - Линия среднего риска показывает тренд
    
    ---
    
    **Статус сервисов:**
    - Показывает доступность внешних API
    - ✅ = настроен и работает
    - ⚠️ = не настроен (отсутствует API key)
    """)
