"""
Визуализация риск-скора с использованием Plotly.

Модуль предоставляет:
- render_risk_gauge() - индикатор риск-скора (0-100)
- render_risk_categories_bar() - распределение по категориям
- render_risk_summary() - комбинированная визуализация
"""

from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import streamlit as st


# Цветовая схема для уровней риска
RISK_COLORS = {
    "low": "#28a745",       # Зелёный
    "medium": "#ffc107",    # Жёлтый
    "high": "#fd7e14",      # Оранжевый
    "critical": "#dc3545",  # Красный
}

# Цвета для gauge зон
GAUGE_STEPS = [
    {"range": [0, 25], "color": "#d4edda"},    # Светло-зелёный (low)
    {"range": [25, 50], "color": "#fff3cd"},   # Светло-жёлтый (medium)
    {"range": [50, 75], "color": "#ffe5d0"},   # Светло-оранжевый (high)
    {"range": [75, 100], "color": "#f8d7da"},  # Светло-красный (critical)
]

# Категории рисков с весами
RISK_CATEGORIES = {
    "legal": {"name": "Правовой", "weight": 0.35, "max": 40, "emoji": "⚖️"},
    "financial": {"name": "Финансовый", "weight": 0.30, "max": 30, "emoji": "💰"},
    "reputation": {"name": "Репутационный", "weight": 0.20, "max": 20, "emoji": "📰"},
    "regulatory": {"name": "Регуляторный", "weight": 0.15, "max": 15, "emoji": "🏛️"},
}


def get_risk_color(score: int) -> str:
    """Получить цвет для риск-скора."""
    if score >= 75:
        return RISK_COLORS["critical"]
    elif score >= 50:
        return RISK_COLORS["high"]
    elif score >= 25:
        return RISK_COLORS["medium"]
    else:
        return RISK_COLORS["low"]


def get_risk_level(score: int) -> str:
    """Получить уровень риска по скору."""
    if score >= 75:
        return "critical"
    elif score >= 50:
        return "high"
    elif score >= 25:
        return "medium"
    else:
        return "low"


def get_risk_level_ru(level: str) -> str:
    """Получить русское название уровня риска."""
    mapping = {
        "low": "Низкий",
        "medium": "Средний",
        "high": "Высокий",
        "critical": "Критический",
    }
    return mapping.get(level, level)


def render_risk_gauge(
    score: int,
    *,
    title: str = "Риск-скор",
    height: int = 300,
    show_delta: bool = False,
    reference_score: Optional[int] = None,
) -> None:
    """
    Отобразить gauge chart для риск-скора.

    Args:
        score: Значение риск-скора (0-100)
        title: Заголовок графика
        height: Высота графика в пикселях
        show_delta: Показывать ли дельту относительно reference
        reference_score: Эталонное значение для сравнения
    """
    score = max(0, min(100, score))
    level = get_risk_level(score)
    level_ru = get_risk_level_ru(level)
    bar_color = get_risk_color(score)

    # Конфигурация gauge
    gauge_config = {
        "axis": {
            "range": [0, 100],
            "tickwidth": 1,
            "tickcolor": "#666",
            "tickvals": [0, 25, 50, 75, 100],
            "ticktext": ["0", "25", "50", "75", "100"],
        },
        "bar": {"color": bar_color, "thickness": 0.75},
        "bgcolor": "white",
        "borderwidth": 2,
        "bordercolor": "#ddd",
        "steps": GAUGE_STEPS,
        "threshold": {
            "line": {"color": "#333", "width": 4},
            "thickness": 0.75,
            "value": score,
        },
    }

    # Режим отображения
    mode = "gauge+number"
    delta_config = None

    if show_delta and reference_score is not None:
        mode = "gauge+number+delta"
        delta_config = {
            "reference": reference_score,
            "increasing": {"color": RISK_COLORS["critical"]},
            "decreasing": {"color": RISK_COLORS["low"]},
        }

    fig = go.Figure(
        go.Indicator(
            mode=mode,
            value=score,
            number={
                "suffix": f" ({level_ru})",
                "font": {"size": 28, "color": bar_color},
            },
            delta=delta_config,
            title={
                "text": title,
                "font": {"size": 18, "color": "#333"},
            },
            gauge=gauge_config,
            domain={"x": [0, 1], "y": [0, 1]},
        )
    )

    fig.update_layout(
        height=height,
        margin={"l": 30, "r": 30, "t": 50, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif"},
    )

    st.plotly_chart(fig, use_container_width=True)


def render_risk_categories_bar(
    categories_data: Optional[Dict[str, int]] = None,
    *,
    factors: Optional[List[Dict[str, Any]]] = None,
    height: int = 300,
    show_weights: bool = True,
) -> None:
    """
    Отобразить bar chart распределения риска по категориям.

    Args:
        categories_data: Словарь {category: score} с баллами по категориям
        factors: Список факторов риска (альтернативный способ получения данных)
        height: Высота графика в пикселях
        show_weights: Показывать ли веса категорий
    """
    # Если данные не переданы, пробуем извлечь из факторов
    if categories_data is None:
        categories_data = _extract_categories_from_factors(factors)

    # Подготовка данных для графика
    category_names = []
    scores = []
    max_scores = []
    colors = []
    hover_texts = []

    for cat_id, cat_info in RISK_CATEGORIES.items():
        score = categories_data.get(cat_id, 0)
        max_score = cat_info["max"]
        weight_pct = int(cat_info["weight"] * 100)

        # Нормализуем скор к максимуму категории
        normalized_score = min(score, max_score)

        label = f"{cat_info['emoji']} {cat_info['name']}"
        if show_weights:
            label += f" ({weight_pct}%)"

        category_names.append(label)
        scores.append(normalized_score)
        max_scores.append(max_score)

        # Цвет зависит от заполненности
        fill_ratio = normalized_score / max_score if max_score > 0 else 0
        if fill_ratio >= 0.75:
            colors.append(RISK_COLORS["critical"])
        elif fill_ratio >= 0.50:
            colors.append(RISK_COLORS["high"])
        elif fill_ratio >= 0.25:
            colors.append(RISK_COLORS["medium"])
        else:
            colors.append(RISK_COLORS["low"])

        hover_texts.append(
            f"<b>{cat_info['name']}</b><br>"
            f"Баллы: {normalized_score}/{max_score}<br>"
            f"Вес: {weight_pct}%"
        )

    # Создание графика
    fig = go.Figure()

    # Фоновые бары (максимальные значения)
    fig.add_trace(
        go.Bar(
            name="Максимум",
            x=category_names,
            y=max_scores,
            marker_color="#e9ecef",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Основные бары (текущие значения)
    fig.add_trace(
        go.Bar(
            name="Текущий риск",
            x=category_names,
            y=scores,
            marker_color=colors,
            text=[f"{s}" for s in scores],
            textposition="outside",
            hovertext=hover_texts,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_layout(
        barmode="overlay",
        height=height,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={
            "tickangle": 0,
            "tickfont": {"size": 11},
        },
        yaxis={
            "title": "Баллы риска",
            "range": [0, max(max_scores) * 1.15],
            "gridcolor": "#eee",
        },
        font={"family": "Arial, sans-serif"},
    )

    st.plotly_chart(fig, use_container_width=True)


def render_risk_factors_by_severity(
    factors: List[Dict[str, Any]],
    *,
    height: int = 250,
) -> None:
    """
    Отобразить pie chart распределения факторов по severity.

    Args:
        factors: Список факторов риска
        height: Высота графика в пикселях
    """
    if not factors:
        st.info("Нет данных о факторах риска")
        return

    # Подсчёт факторов по severity
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for factor in factors:
        severity = factor.get("severity", "low")
        if severity in severity_counts:
            severity_counts[severity] += 1

    # Фильтруем нулевые значения
    labels = []
    values = []
    colors = []

    severity_names = {
        "critical": "Критические",
        "high": "Высокие",
        "medium": "Средние",
        "low": "Низкие",
    }

    for severity, count in severity_counts.items():
        if count > 0:
            labels.append(severity_names[severity])
            values.append(count)
            colors.append(RISK_COLORS[severity])

    if not values:
        st.info("Факторы риска не обнаружены")
        return

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            marker_colors=colors,
            hole=0.4,
            textinfo="label+value",
            textposition="outside",
            hovertemplate="<b>%{label}</b><br>Количество: %{value}<extra></extra>",
        )
    )

    fig.update_layout(
        height=height,
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        font={"family": "Arial, sans-serif"},
        annotations=[
            {
                "text": f"Всего<br>{sum(values)}",
                "x": 0.5,
                "y": 0.5,
                "font_size": 14,
                "showarrow": False,
            }
        ],
    )

    st.plotly_chart(fig, use_container_width=True)


def render_risk_summary(
    risk_assessment: Dict[str, Any],
    *,
    show_factors_chart: bool = True,
) -> None:
    """
    Отобразить комбинированную визуализацию риск-скора.

    Args:
        risk_assessment: Словарь с данными оценки рисков
            - score: int (0-100)
            - level: str (low/medium/high/critical)
            - factors: List[Dict] (опционально)
            - categories: Dict[str, int] (опционально)
        show_factors_chart: Показывать ли pie chart факторов
    """
    score = risk_assessment.get("score", 0)
    level = risk_assessment.get("level", get_risk_level(score))
    factors = risk_assessment.get("factors", [])
    categories = risk_assessment.get("categories", {})

    # Заголовок секции
    st.markdown("### 📊 Визуализация риск-скора")

    # Две колонки: gauge и bar chart
    col1, col2 = st.columns([1, 1])

    with col1:
        render_risk_gauge(score, title="Общий риск-скор")

    with col2:
        # Если есть категории - показываем их, иначе извлекаем из факторов
        if categories:
            render_risk_categories_bar(categories)
        elif factors:
            render_risk_categories_bar(factors=factors)
        else:
            # Показываем пустой график с нулевыми значениями
            render_risk_categories_bar({})

    # Pie chart факторов (если есть)
    if show_factors_chart and factors:
        with st.expander("📋 Распределение факторов по критичности", expanded=False):
            render_risk_factors_by_severity(factors)


def _extract_categories_from_factors(
    factors: Optional[List[Dict[str, Any]]],
) -> Dict[str, int]:
    """
    Извлечь баллы категорий из списка факторов.

    Args:
        factors: Список факторов риска

    Returns:
        Словарь {category: total_score}
    """
    if not factors:
        return {}

    categories: Dict[str, int] = {}

    for factor in factors:
        category = factor.get("category", "").lower()
        score = factor.get("score_contribution", 0)

        if category in RISK_CATEGORIES:
            categories[category] = categories.get(category, 0) + score

    return categories


__all__ = [
    "render_risk_gauge",
    "render_risk_categories_bar",
    "render_risk_factors_by_severity",
    "render_risk_summary",
    "get_risk_color",
    "get_risk_level",
    "get_risk_level_ru",
    "RISK_CATEGORIES",
    "RISK_COLORS",
]
