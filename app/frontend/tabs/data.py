from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.validators import validate_inn
from app.frontend.lib.ui import section_header, render_payload, info_box


def render(api: ApiClient) -> None:
    st.header("🔍 Внешние данные")
    
    info_box(
        "Этот раздел позволяет получить данные о компании из различных источников: "
        "реестры, судебные дела, финансовая информация."
    )

    section_header("Источники по ИНН", emoji="📦", help_text="DaData, Casebook, Инфосфера")
    inn = st.text_input("ИНН", placeholder="7707083893", max_chars=12)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        btn_all = st.button("Вместе", type="primary")
    with c2:
        btn_dadata = st.button("DaData")
    with c3:
        btn_casebook = st.button("Casebook")
    with c4:
        btn_infosphere = st.button("Инфосфера")

    if btn_all or btn_dadata or btn_casebook or btn_infosphere:
        is_valid, error_msg = validate_inn(inn, required=True)
        if not is_valid:
            st.error(f"❌ {error_msg}")
        else:
            results: Dict[str, Any] = {}
            with st.spinner("Запрашиваю данные..."):
                if btn_all:
                    results["Все источники"] = api.get(f"/data/client/info/{inn.strip()}")
                else:
                    if btn_dadata:
                        results["DaData"] = api.get(f"/data/client/dadata/{inn.strip()}")
                    if btn_casebook:
                        results["Casebook"] = api.get(f"/data/client/casebook/{inn.strip()}")
                    if btn_infosphere:
                        results["Инфосфера"] = api.get(f"/data/client/infosphere/{inn.strip()}")

            for title, payload in results.items():
                render_payload(payload, title=f"📦 {title}", expanded=True, show_status=False)

    st.divider()

    section_header("Веб-поиск", emoji="🔎", help_text="Perplexity AI, Tavily")
    col1, col2 = st.columns([1, 2])
    with col1:
        search_inn = st.text_input("ИНН для поиска", key="search_inn", placeholder="7707083893", max_chars=12)
    with col2:
        query = st.text_input("Поисковый запрос", key="search_query", placeholder="судебные дела, банкротство, новости")

    colp1, colp2 = st.columns(2)
    with colp1:
        perplexity_recency = st.selectbox(
            "Perplexity: актуальность",
            options=["day", "week", "month"],
            format_func=lambda x: {"day": "День", "week": "Неделя", "month": "Месяц"}[x],
            index=2,
        )
    with colp2:
        tavily_depth = st.selectbox(
            "Tavily: глубина поиска",
            options=["basic", "advanced"],
            format_func=lambda x: {"basic": "Базовая", "advanced": "Расширенная"}[x],
            index=0
        )
    max_results = st.slider("Tavily: максимум результатов", min_value=1, max_value=10, value=5)
    include_answer = st.checkbox("Tavily: включить краткий ответ", value=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        do_p = st.button("Искать в Perplexity", type="primary")
    with b2:
        do_t = st.button("Искать в Tavily", type="primary")
    with b3:
        do_both = st.button("Искать в обоих")

    if do_p or do_t or do_both:
        is_valid, error_msg = validate_inn(search_inn, required=True)
        if not is_valid:
            st.error(f"❌ {error_msg}")
            return
        if not (query or "").strip():
            st.error("❌ Поисковый запрос обязателен")
            return

        outputs: Dict[str, Any] = {}

        with st.spinner("Выполняю поиск..."):
            if do_p or do_both:
                outputs["Perplexity"] = api.post(
                    "/data/search/perplexity",
                    json={"inn": search_inn.strip(), "search_query": query.strip(), "search_recency": perplexity_recency},
                )
            if do_t or do_both:
                outputs["Tavily"] = api.post(
                    "/data/search/tavily",
                    json={
                        "inn": search_inn.strip(),
                        "search_query": query.strip(),
                        "search_depth": tavily_depth,
                        "max_results": int(max_results),
                        "include_answer": bool(include_answer),
                    },
                )

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
                                # Не вкладывать expander в expander - показать сразу
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

