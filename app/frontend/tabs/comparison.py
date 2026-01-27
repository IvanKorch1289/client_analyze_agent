"""
Comparison Tab: Side-by-side сравнение двух отчётов анализа клиентов.

Sprint 2: Analysis Comparison feature.
"""

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.ui import section_header


def render_comparison_tab(api: ApiClient):
    """Рендерит вкладку сравнения отчётов."""
    section_header("Сравнение отчётов", emoji="🔄")

    st.markdown(
        """
    **Сравните два анализа клиента side-by-side** для отслеживания изменений
    в риск-оценке, новых находках и качестве данных.

    Полезно для:
    - Отслеживания динамики риска компании
    - Оценки эффективности дополнительных инструкций (feedback)
    - Сравнения анализов до и после получения новых данных
    """
    )

    # Шаг 1: Выбор компании по ИНН
    st.divider()
    st.subheader("1️⃣ Выберите компанию")

    col1, col2 = st.columns([3, 1])

    with col1:
        inn = st.text_input(
            "ИНН компании",
            placeholder="1234567890",
            help="Введите ИНН компании для поиска всех анализов",
        )

    with col2:
        search_clicked = st.button("🔍 Найти анализы", use_container_width=True, type="primary")

    if not search_clicked and not st.session_state.get("comparison_reports"):
        st.info("👆 Введите ИНН компании и нажмите 'Найти анализы' для начала")
        return

    if search_clicked:
        if not inn or not inn.isdigit() or len(inn) not in (10, 12):
            st.error("❌ Введите корректный ИНН (10 или 12 цифр)")
            return

        with st.spinner("🔍 Поиск анализов..."):
            try:
                response = api.get(f"/reports/inn/{inn}")

                if response and response.get("status") == "success":
                    reports = response.get("reports", [])

                    if not reports:
                        st.warning(f"⚠️ Не найдено анализов для ИНН {inn}")
                        return

                    if len(reports) < 2:
                        st.warning(f"⚠️ Найден только {len(reports)} анализ. Для сравнения нужно минимум 2 анализа.")
                        return

                    st.session_state["comparison_reports"] = reports
                    st.session_state["comparison_inn"] = inn
                    st.success(f"✅ Найдено {len(reports)} анализов для сравнения")
                else:
                    st.error("❌ Ошибка при поиске анализов")
                    return

            except Exception as e:
                st.error(f"❌ Ошибка: {str(e)}")
                return

    # Шаг 2: Выбор двух отчётов
    if st.session_state.get("comparison_reports"):
        reports = st.session_state["comparison_reports"]

        st.divider()
        st.subheader("2️⃣ Выберите два отчёта для сравнения")

        # Форматируем отчёты для selectbox
        def format_report_option(report):
            client_name = report.get("client_name", "Неизвестная компания")
            created_at = report.get("created_at", "")
            report_id = report.get("report_id", "")

            # Извлекаем риск-скор если есть
            report_data = report.get("report_data", {})
            risk_assessment = report_data.get("risk_assessment", {})
            risk_score = risk_assessment.get("score", "?")
            risk_level = risk_assessment.get("level", "unknown")

            # Иконки для уровня риска
            risk_emoji = {
                "low": "✅",
                "medium": "⚠️",
                "high": "🔴",
                "critical": "🚨",
                "unknown": "❓",
            }.get(risk_level, "❓")

            return f"{risk_emoji} {client_name} | Risk: {risk_score}/100 | {created_at[:19]} | ID: {report_id[:8]}..."

        report_options = {format_report_option(r): r for r in reports}

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Отчёт A** (обычно старый)")
            report1_label = st.selectbox(
                "Выберите первый отчёт",
                options=list(report_options.keys()),
                key="report1_selector",
                label_visibility="collapsed",
            )
            report1 = report_options[report1_label]

        with col2:
            st.markdown("**Отчёт B** (обычно новый)")
            report2_label = st.selectbox(
                "Выберите второй отчёт",
                options=list(report_options.keys()),
                key="report2_selector",
                label_visibility="collapsed",
            )
            report2 = report_options[report2_label]

        # Проверяем что выбраны разные отчёты
        if report1.get("report_id") == report2.get("report_id"):
            st.warning("⚠️ Выберите два разных отчёта для сравнения")
            return

        # Кнопка сравнения
        st.divider()
        compare_clicked = st.button("🔄 Сравнить отчёты", use_container_width=True, type="primary")

        if compare_clicked:
            with st.spinner("🔄 Сравнение отчётов..."):
                try:
                    comparison = api.get(f"/reports/compare/{report1['report_id']}/{report2['report_id']}")

                    if comparison and comparison.get("status") == "success":
                        st.session_state["comparison_result"] = comparison
                    else:
                        st.error("❌ Ошибка при сравнении отчётов")
                        return

                except Exception as e:
                    st.error(f"❌ Ошибка: {str(e)}")
                    return

    # Шаг 3: Отображение результатов сравнения
    if st.session_state.get("comparison_result"):
        comparison = st.session_state["comparison_result"]

        st.divider()
        st.subheader("3️⃣ Результаты сравнения")

        report1_info = comparison["report1"]
        report2_info = comparison["report2"]
        diff = comparison["diff"]
        summary = comparison["summary"]

        # Сводка изменений
        st.markdown("### 📊 Сводка изменений")

        improvements = summary.get("improvements", [])
        regressions = summary.get("regressions", [])

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Всего изменений",
                summary.get("total_changes", 0),
                help="Количество метрик, которые изменились",
            )

        with col2:
            st.metric(
                "Улучшения",
                len(improvements),
                delta=len(improvements) if improvements else None,
                delta_color="normal",
                help="Позитивные изменения",
            )

        with col3:
            st.metric(
                "Ухудшения",
                len(regressions),
                delta=-len(regressions) if regressions else None,
                delta_color="inverse",
                help="Негативные изменения",
            )

        # Детали улучшений и ухудшений
        if improvements or regressions:
            col1, col2 = st.columns(2)

            with col1:
                if improvements:
                    st.success("**✅ Улучшения:**")
                    for improvement in improvements:
                        st.markdown(f"- {improvement}")

            with col2:
                if regressions:
                    st.error("**⚠️ Ухудшения:**")
                    for regression in regressions:
                        st.markdown(f"- {regression}")

        # Side-by-side сравнение метрик
        st.divider()
        st.markdown("### 🔍 Детальное сравнение")

        # Risk Score
        with st.expander("⚠️ **Риск-оценка**", expanded=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Отчёт A**")
                st.metric(
                    "Risk Score",
                    diff["risk_score"]["old"],
                    help=f"Уровень: {diff['risk_level']['old']}",
                )

            with col2:
                st.markdown("**Отчёт B**")
                st.metric(
                    "Risk Score",
                    diff["risk_score"]["new"],
                    delta=diff["risk_score"]["delta"],
                    delta_color="inverse",  # Increase is bad
                    help=f"Уровень: {diff['risk_level']['new']}",
                )

            with col3:
                st.markdown("**Изменение**")
                delta = diff["risk_score"]["delta"]
                if delta > 0:
                    st.error(f"↑ +{delta} (хуже)")
                elif delta < 0:
                    st.success(f"↓ {delta} (лучше)")
                else:
                    st.info("= Без изменений")

            # Risk Level
            if diff["risk_level"]["changed"]:
                st.markdown("**Уровень риска изменился:**")
                st.markdown(f"`{diff['risk_level']['old']}` → `{diff['risk_level']['new']}`")

        # Risk Factors
        with st.expander("🔴 **Факторы риска**", expanded=diff["risk_factors"]["changed"]):
            added = diff["risk_factors"]["added"]
            removed = diff["risk_factors"]["removed"]

            if added:
                st.error("**Новые факторы риска:**")
                for factor in added:
                    st.markdown(f"- ➕ {factor}")

            if removed:
                st.success("**Устранённые факторы риска:**")
                for factor in removed:
                    st.markdown(f"- ➖ {factor}")

            if not added and not removed:
                st.info("Факторы риска не изменились")

        # Findings Count
        with st.expander("📋 **Находки и рекомендации**"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Findings (находки)**")
                st.metric(
                    "Отчёт A",
                    diff["findings_count"]["old"],
                )
                st.metric(
                    "Отчёт B",
                    diff["findings_count"]["new"],
                    delta=diff["findings_count"]["delta"],
                )

            with col2:
                st.markdown("**Data Quality**")
                st.metric(
                    "Отчёт A",
                    f"{diff['data_quality']['old']}%",
                )
                st.metric(
                    "Отчёт B",
                    f"{diff['data_quality']['new']}%",
                    delta=f"{diff['data_quality']['delta']}%",
                    delta_color="normal",
                )

        # Дополнительная информация
        with st.expander("ℹ️ **Дополнительная информация**"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Отчёт A**")
                st.markdown(f"- **ID:** `{report1_info['id'][:16]}...`")
                st.markdown(f"- **Дата:** {report1_info['created_at'][:19]}")
                st.markdown(f"- **Версия:** {report1_info['metrics']['version']}")
                st.markdown(f"- **Успешных источников:** {report1_info['metrics']['successful_sources']}")

            with col2:
                st.markdown("**Отчёт B**")
                st.markdown(f"- **ID:** `{report2_info['id'][:16]}...`")
                st.markdown(f"- **Дата:** {report2_info['created_at'][:19]}")
                st.markdown(f"- **Версия:** {report2_info['metrics']['version']}")
                st.markdown(f"- **Успешных источников:** {report2_info['metrics']['successful_sources']}")


__all__ = ["render_comparison_tab"]
