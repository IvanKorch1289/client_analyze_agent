from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.api_client import ApiClient


def _valid_inn_required(inn: str) -> bool:
    inn = (inn or "").strip()
    return inn.isdigit() and len(inn) in (10, 12)


def render(api: ApiClient) -> None:
    st.header("Внешние данные")

    st.subheader("A) Источники по ИНН (DaData / Casebook / Инфосфера)")
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
        if not _valid_inn_required(inn):
            st.error("ИНН должен содержать 10 или 12 цифр")
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
                with st.expander(title, expanded=True):
                    if payload is None:
                        st.warning("Нет данных (ошибка запроса)")
                    else:
                        st.json(payload)

    st.divider()

    st.subheader("B) Веб-поиск (Perplexity / Tavily)")
    col1, col2 = st.columns([1, 2])
    with col1:
        search_inn = st.text_input("ИНН для поиска", key="search_inn", placeholder="7707083893", max_chars=12)
    with col2:
        query = st.text_input("Query", key="search_query", placeholder="судебные дела, банкротство, новости")

    colp1, colp2 = st.columns(2)
    with colp1:
        perplexity_recency = st.selectbox(
            "Perplexity recency",
            options=["day", "week", "month"],
            index=2,
        )
    with colp2:
        tavily_depth = st.selectbox("Tavily depth", options=["basic", "advanced"], index=0)
    max_results = st.slider("Tavily max_results", min_value=1, max_value=10, value=5)
    include_answer = st.checkbox("Tavily include_answer", value=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        do_p = st.button("Искать в Perplexity", type="primary")
    with b2:
        do_t = st.button("Искать в Tavily", type="primary")
    with b3:
        do_both = st.button("Искать в обоих")

    if do_p or do_t or do_both:
        if not _valid_inn_required(search_inn):
            st.error("ИНН должен содержать 10 или 12 цифр")
            return
        if not (query or "").strip():
            st.error("query обязателен")
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
            with st.expander(source, expanded=True):
                if payload is None:
                    st.warning("Нет данных (ошибка запроса)")
                    continue

                if source == "Perplexity" and isinstance(payload, dict):
                    if payload.get("status") == "success":
                        st.markdown(payload.get("content", "") or "")
                        cites = payload.get("citations") or []
                        if cites:
                            with st.expander("Источники", expanded=False):
                                for c in cites:
                                    st.write(f"- {c}")
                    else:
                        st.json(payload)
                elif source == "Tavily" and isinstance(payload, dict):
                    if payload.get("status") == "success":
                        answer = payload.get("answer") or ""
                        if answer:
                            st.markdown(f"**Краткий ответ:** {answer}")
                        results = payload.get("results") or []
                        if results:
                            st.markdown("**Ссылки / сниппеты:**")
                            for item in results:
                                title = item.get("title") or "Без заголовка"
                                url = item.get("url") or ""
                                snippet = item.get("content") or item.get("snippet") or ""
                                st.markdown(f"- **{title}**")
                                if url:
                                    st.caption(url)
                                if snippet:
                                    st.caption(snippet[:400] + ("..." if len(snippet) > 400 else ""))
                    else:
                        st.json(payload)
                else:
                    st.json(payload)

