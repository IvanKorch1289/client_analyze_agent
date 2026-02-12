from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.ui import get_admin_token as _get_token, info_box, render_payload, section_header
from app.frontend.lib.validators import validate_inn


def render(api: ApiClient) -> None:
    st.header("🔍 Внешние данные")

    info_box(
        "Этот раздел позволяет получить данные о компании из различных источников: "
        "реестры, судебные дела, финансовая информация."
    )

    section = st.selectbox(
        "Выберите секцию",
        options=[
            "Источники по ИНН",
            "Веб-поиск",
            "Отложенный сбор данных",
        ],
        index=0,
        key="data_section",
    )

    st.divider()

    if section == "Источники по ИНН":
        _render_inn_sources_section(api)
    elif section == "Веб-поиск":
        _render_web_search_section(api)
    elif section == "Отложенный сбор данных":
        _render_scheduled_section(api)


def _render_inn_sources_section(api: ApiClient) -> None:
    section_header("Источники по ИНН", emoji="📦", help_text="DaData, Casebook, Инфосфера")
    inn = st.text_input("ИНН", placeholder="7707083893", max_chars=12, key="inn_sources_inn")

    st.markdown("**Выберите источники:**")
    c1, c2, c3 = st.columns(3)
    with c1:
        chk_dadata = st.checkbox("DaData", value=False, key="chk_dadata")
    with c2:
        chk_casebook = st.checkbox("Casebook", value=False, key="chk_casebook")
    with c3:
        chk_infosphere = st.checkbox("Инфосфера", value=False, key="chk_infosphere")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        btn_all = st.button("Вместе (все источники)", type="primary", key="btn_inn_all")
    with btn_col2:
        btn_fetch = st.button("Получить данные", key="btn_inn_fetch")

    if btn_all or btn_fetch:
        is_valid, error_msg = validate_inn(inn, required=True)
        if not is_valid:
            st.error(f"❌ {error_msg}")
            return

        results: Dict[str, Any] = {}
        inn_clean = inn.strip()

        with st.spinner("Запрашиваю данные..."):
            if btn_all:
                results["Все источники"] = api.get(f"/data/client/info/{inn_clean}", admin_token=_get_token())
            else:
                selected_any = chk_dadata or chk_casebook or chk_infosphere
                if not selected_any:
                    st.warning("⚠️ Выберите хотя бы один источник")
                    return

                if chk_dadata:
                    results["DaData"] = api.get(f"/data/client/dadata/{inn_clean}", admin_token=_get_token())
                if chk_casebook:
                    results["Casebook"] = api.get(f"/data/client/casebook/{inn_clean}", admin_token=_get_token())
                if chk_infosphere:
                    results["Инфосфера"] = api.get(f"/data/client/infosphere/{inn_clean}", admin_token=_get_token())

        for title, payload in results.items():
            render_payload(payload, title=f"📦 {title}", expanded=True, show_status=False)


def _render_web_search_section(api: ApiClient) -> None:
    section_header("Веб-поиск", emoji="🔎", help_text="Perplexity AI, Tavily")

    col1, col2 = st.columns([1, 2])
    with col1:
        search_inn = st.text_input("ИНН для поиска", key="search_inn", placeholder="7707083893", max_chars=12)
    with col2:
        query = st.text_input(
            "Поисковый запрос",
            key="search_query",
            placeholder="судебные дела, банкротство, новости",
        )

    st.markdown("**Выберите поисковые системы:**")
    ws_c1, ws_c2 = st.columns(2)
    with ws_c1:
        chk_perplexity = st.checkbox("Perplexity", value=False, key="chk_perplexity")
    with ws_c2:
        chk_tavily = st.checkbox("Tavily", value=False, key="chk_tavily")

    colp1, colp2 = st.columns(2)
    with colp1:
        perplexity_recency = st.selectbox(
            "Perplexity: актуальность",
            options=["day", "week", "month"],
            format_func=lambda x: {"day": "День", "week": "Неделя", "month": "Месяц"}[x],
            index=2,
            key="perplexity_recency",
        )
    with colp2:
        tavily_depth = st.selectbox(
            "Tavily: глубина поиска",
            options=["basic", "advanced"],
            format_func=lambda x: {"basic": "Базовая", "advanced": "Расширенная"}[x],
            index=0,
            key="tavily_depth",
        )
    max_results = st.slider(
        "Tavily: максимум результатов",
        min_value=1,
        max_value=10,
        value=5,
        key="tavily_max_results",
    )
    include_answer = st.checkbox("Tavily: включить краткий ответ", value=True, key="tavily_include_answer")

    btn_search = st.button("Искать", type="primary", key="btn_web_search")

    if btn_search:
        is_valid, error_msg = validate_inn(search_inn, required=True)
        if not is_valid:
            st.error(f"❌ {error_msg}")
            return
        if not (query or "").strip():
            st.error("❌ Поисковый запрос обязателен")
            return
        if not chk_perplexity and not chk_tavily:
            st.warning("⚠️ Выберите хотя бы одну поисковую систему")
            return

        outputs: Dict[str, Any] = {}
        inn_clean = search_inn.strip()
        query_clean = query.strip()

        with st.spinner("Выполняю поиск..."):
            if chk_perplexity:
                outputs["Perplexity"] = api.post(
                    "/data/search/perplexity",
                    json={
                        "inn": inn_clean,
                        "search_query": query_clean,
                        "search_recency": perplexity_recency,
                    },
                    admin_token=_get_token(),
                )
            if chk_tavily:
                outputs["Tavily"] = api.post(
                    "/data/search/tavily",
                    json={
                        "inn": inn_clean,
                        "search_query": query_clean,
                        "search_depth": tavily_depth,
                        "max_results": int(max_results),
                        "include_answer": bool(include_answer),
                    },
                    admin_token=_get_token(),
                )

        _render_search_results(outputs)


def _render_search_results(outputs: Dict[str, Any]) -> None:
    for source, payload in outputs.items():
        st.markdown(f"#### 🔎 {source}")

        if payload is None:
            st.warning("⚠️ Нет данных (ошибка запроса)")
            continue

        if source == "Perplexity" and isinstance(payload, dict):
            if payload.get("status") == "success":
                content = payload.get("content", "") or ""
                if content:
                    st.markdown("**📝 Результат поиска:**")
                    st.markdown(content)

                cites = payload.get("citations") or []
                if cites:
                    st.markdown("**📚 Источники:**")
                    for i, c in enumerate(cites, 1):
                        st.caption(f"{i}. {c}")
            else:
                st.json(payload)

        elif source == "Tavily" and isinstance(payload, dict):
            if payload.get("status") == "success":
                answer = payload.get("answer") or ""
                if answer:
                    st.info(f"💡 **Краткий ответ:** {answer}")

                results = payload.get("results") or []
                if results:
                    st.markdown(f"**🔗 Найдено источников: {len(results)}**")
                    for i, item in enumerate(results, 1):
                        title = item.get("title") or "Без заголовка"
                        url = item.get("url") or ""
                        snippet = item.get("content") or item.get("snippet") or ""
                        score = item.get("score", 0)

                        st.markdown(f"**{i}. {title}**")
                        if score:
                            st.caption(f"Релевантность: {score:.2f}")
                        if url:
                            st.caption(f"🔗 {url}")
                        if snippet:
                            st.text_area(
                                f"Содержание #{i}",
                                snippet[:800] + ("..." if len(snippet) > 800 else ""),
                                height=150,
                                key=f"tavily_snippet_{i}",
                                disabled=True,
                            )
                        st.divider()
            else:
                st.json(payload)
        else:
            st.json(payload)

        st.divider()


def _render_scheduled_section(api: ApiClient) -> None:
    section_header(
        "Отложенный сбор данных",
        emoji="⏰",
        help_text="Запланировать сбор данных на будущее",
    )

    scheduled_inn = st.text_input("ИНН", placeholder="7707083893", max_chars=12, key="scheduled_inn")

    st.markdown("**Выберите источники для сбора:**")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    with sc1:
        sch_dadata = st.checkbox("DaData", value=False, key="sch_dadata")
    with sc2:
        sch_casebook = st.checkbox("Casebook", value=False, key="sch_casebook")
    with sc3:
        sch_infosphere = st.checkbox("Инфосфера", value=False, key="sch_infosphere")
    with sc4:
        sch_perplexity = st.checkbox("Perplexity", value=False, key="sch_perplexity")
    with sc5:
        sch_tavily = st.checkbox("Tavily", value=False, key="sch_tavily")

    schedule_type = st.radio(
        "Когда выполнить:",
        options=["delay", "datetime"],
        format_func=lambda x: {
            "delay": "Через N минут",
            "datetime": "В конкретное время",
        }[x],
        horizontal=True,
        key="schedule_type",
    )

    schedule_at: str = ""
    delay_minutes: int = 30
    if schedule_type == "delay":
        delay_minutes = st.number_input(
            "Через сколько минут",
            min_value=1,
            max_value=10080,
            value=30,
            step=5,
            key="delay_minutes",
        )
        run_time = datetime.now() + timedelta(minutes=int(delay_minutes))
        schedule_at = run_time.isoformat()
        st.caption(f"Запланировано на: {run_time.strftime('%Y-%m-%d %H:%M')}")
    else:
        col_date, col_time = st.columns(2)
        with col_date:
            sch_date = st.date_input("Дата", value=datetime.now().date(), key="sch_date")
        with col_time:
            sch_time = st.time_input("Время", value=datetime.now().time(), key="sch_time")
        if sch_date and sch_time:
            run_time = datetime.combine(sch_date, sch_time)
            schedule_at = run_time.isoformat()

    needs_search_query = sch_perplexity or sch_tavily
    scheduled_query = ""
    sch_perplexity_recency = "month"
    sch_tavily_depth = "basic"
    sch_tavily_max_results = 5
    sch_tavily_include_answer = True

    if needs_search_query:
        scheduled_query = st.text_input(
            "Поисковый запрос (для Perplexity/Tavily)",
            key="scheduled_query",
            placeholder="судебные дела, банкротство, новости",
        )
        if sch_perplexity:
            sch_perplexity_recency = st.selectbox(
                "Perplexity: актуальность",
                options=["day", "week", "month"],
                format_func=lambda x: {
                    "day": "День",
                    "week": "Неделя",
                    "month": "Месяц",
                }[x],
                index=2,
                key="sch_perplexity_recency",
            )
        if sch_tavily:
            col_td, col_tm = st.columns(2)
            with col_td:
                sch_tavily_depth = st.selectbox(
                    "Tavily: глубина",
                    options=["basic", "advanced"],
                    format_func=lambda x: {
                        "basic": "Базовая",
                        "advanced": "Расширенная",
                    }[x],
                    index=0,
                    key="sch_tavily_depth",
                )
            with col_tm:
                sch_tavily_max_results = st.slider("Tavily: макс. результатов", 1, 10, 5, key="sch_tavily_max_results")
            sch_tavily_include_answer = st.checkbox(
                "Tavily: краткий ответ", value=True, key="sch_tavily_include_answer"
            )

    btn_schedule = st.button("Запланировать", type="primary", key="btn_schedule")

    if btn_schedule:
        is_valid, error_msg = validate_inn(scheduled_inn, required=True)
        if not is_valid:
            st.error(f"❌ {error_msg}")
            return

        sources: List[str] = []
        if sch_dadata:
            sources.append("dadata")
        if sch_casebook:
            sources.append("casebook")
        if sch_infosphere:
            sources.append("infosphere")
        if sch_perplexity:
            sources.append("perplexity")
        if sch_tavily:
            sources.append("tavily")

        if not sources:
            st.warning("⚠️ Выберите хотя бы один источник")
            return

        if needs_search_query and not (scheduled_query or "").strip():
            st.error("❌ Поисковый запрос обязателен для Perplexity/Tavily")
            return

        if not schedule_at:
            st.error("❌ Укажите время выполнения")
            return

        payload: dict = {
            "inn": scheduled_inn.strip(),
            "sources": sources,
        }

        if schedule_type == "delay":
            payload["delay_minutes"] = int(delay_minutes)
        else:
            payload["run_date"] = schedule_at

        if needs_search_query:
            payload["search_query"] = scheduled_query.strip()
            payload["perplexity_recency"] = sch_perplexity_recency
            payload["tavily_depth"] = sch_tavily_depth
            payload["tavily_max_results"] = sch_tavily_max_results
            payload["tavily_include_answer"] = sch_tavily_include_answer

        with st.spinner("Планирую задачу..."):
            result = api.post("/scheduler/schedule-data-fetch", json=payload, admin_token=_get_token())

        if result:
            if isinstance(result, dict) and result.get("task_id"):
                st.success("✅ Задача успешно запланирована!")
                st.write(f"**ID задачи:** `{result.get('task_id')}`")
                st.write(f"**Выполнение:** `{result.get('run_date')}`")
            elif isinstance(result, dict) and result.get("detail"):
                st.error(f"❌ Ошибка: {result.get('detail')}")
            else:
                st.json(result)
