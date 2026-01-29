"""
Streamlit вкладка: RAG / База знаний.

Функциональность:
- Индексация отчётов (кнопка)
- Загрузка файлов (PDF, DOCX, TXT)
- Семантический поиск
- Просмотр проиндексированных отчётов и документов
- Статистика RAG
"""

from __future__ import annotations


import streamlit as st

from app.frontend.api_client import ApiClient


def render(api: ApiClient, *, admin_token: str) -> None:
    st.header("RAG / База знаний")

    section = st.selectbox(
        "Раздел",
        options=[
            "Индексация отчётов",
            "Загрузка документов",
            "Семантический поиск",
            "Проиндексированные данные",
            "Статистика",
        ],
        index=0,
    )

    st.divider()

    if section == "Индексация отчётов":
        _render_report_indexing(api, admin_token)
    elif section == "Загрузка документов":
        _render_document_upload(api, admin_token)
    elif section == "Семантический поиск":
        _render_semantic_search(api, admin_token)
    elif section == "Проиндексированные данные":
        _render_indexed_data(api, admin_token)
    elif section == "Статистика":
        _render_stats(api, admin_token)


def _render_report_indexing(api: ApiClient, admin_token: str) -> None:
    st.subheader("Индексация отчётов в RAG")

    st.info(
        "Введите ID отчёта из Tarantool для индексации в векторную БД. "
        "После индексации отчёт будет доступен для семантического поиска "
        "и обогащения будущих анализов."
    )

    report_id = st.text_input(
        "ID отчёта",
        placeholder="report:abc123...",
        help="ID из Tarantool (можно найти в разделе Утилиты > Управление отчётами)",
    )

    if st.button("Добавить в базу знаний RAG", type="primary", disabled=not report_id):
        if report_id:
            result = api.post(
                f"/rag/reports/{report_id}/index",
                admin_token=admin_token,
            )
            if result is not None:
                st.success(
                    f"Отчёт проиндексирован!\n"
                    f"- Клиент: {result.get('client_name', 'N/A')}\n"
                    f"- ИНН: {result.get('inn', 'N/A')}\n"
                    f"- Vector ID: {result.get('vector_id', 'N/A')}"
                )

    st.divider()

    # Поиск похожих отчётов
    st.subheader("Поиск похожих отчётов")
    similar_report_id = st.text_input(
        "ID отчёта для поиска похожих",
        placeholder="report:abc123...",
        key="similar_report_id",
    )
    k = st.slider("Количество результатов", 1, 20, 5, key="similar_k")

    if st.button("Найти похожие", disabled=not similar_report_id):
        if similar_report_id:
            result = api.get(
                f"/rag/reports/{similar_report_id}/similar",
                params={"k": k},
                admin_token=admin_token,
            )
            if result is not None:
                similar = result.get("similar", [])
                if similar:
                    for i, item in enumerate(similar, 1):
                        meta = item.get("metadata", {})
                        distance = item.get("distance")
                        similarity = f"{1 - distance:.0%}" if distance is not None else "N/A"

                        with st.expander(
                            f"{i}. {meta.get('client_name', 'N/A')} "
                            f"(ИНН: {meta.get('inn', 'N/A')}) — "
                            f"схожесть: {similarity}"
                        ):
                            st.json(meta)
                            doc = item.get("document", "")
                            if doc:
                                st.text_area("Содержимое", doc, height=150, disabled=True)
                else:
                    st.info("Похожих отчётов не найдено")


def _render_document_upload(api: ApiClient, admin_token: str) -> None:
    st.subheader("Загрузка документов")

    st.info(
        "Загрузите PDF, DOCX или TXT файл для индексации в базе знаний. "
        "Текст будет извлечён, PII данные маскированы, и содержимое "
        "станет доступным для семантического поиска."
    )

    uploaded_file = st.file_uploader(
        "Выберите файл",
        type=["pdf", "docx", "txt", "md"],
        help="Максимальный размер: 10MB",
    )

    if uploaded_file and st.button("Загрузить в RAG", type="primary"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        result = api.upload_file(
            "/rag/documents/upload",
            files=files,
            admin_token=admin_token,
        )
        if result is not None:
            st.success(
                f"Документ загружен!\n"
                f"- Файл: {result.get('filename', 'N/A')}\n"
                f"- Чанков: {result.get('chunk_count', 0)}\n"
                f"- Длина текста: {result.get('text_length', 0)} символов\n"
                f"- PII маскировка: {'Да' if result.get('pii_masked') else 'Нет'}"
            )


def _render_semantic_search(api: ApiClient, admin_token: str) -> None:
    st.subheader("Семантический поиск")

    st.info(
        "Поиск по смыслу в проиндексированных отчётах и документах. Введите запрос на русском или английском языке."
    )

    query = st.text_area(
        "Поисковый запрос",
        placeholder="Например: компании с долгами по налогам и судебными разбирательствами",
        height=100,
    )

    col1, col2 = st.columns(2)
    with col1:
        k = st.slider("Количество результатов", 1, 50, 10, key="search_k")
    with col2:
        collection = st.selectbox(
            "Коллекция",
            options=["Все", "Отчёты", "Документы"],
            index=0,
        )

    collection_map = {"Все": None, "Отчёты": "reports", "Документы": "documents"}

    if st.button("Поиск", type="primary", disabled=not query):
        if query:
            payload = {
                "query": query,
                "k": k,
                "collection": collection_map.get(collection),
            }
            result = api.post(
                "/rag/search",
                json=payload,
                admin_token=admin_token,
            )
            if result is not None:
                results = result.get("results", [])
                st.write(f"Найдено: **{len(results)}** результатов")

                for i, item in enumerate(results, 1):
                    meta = item.get("metadata", {})
                    distance = item.get("distance")
                    similarity = f"{1 - distance:.0%}" if distance is not None else "N/A"
                    doc_type = meta.get("doc_type", "unknown")
                    label = meta.get("client_name") or meta.get("filename") or item.get("id", "N/A")

                    with st.expander(f"{i}. [{doc_type}] {label} — схожесть: {similarity}"):
                        st.json(meta)
                        doc = item.get("document", "")
                        if doc:
                            st.text_area(
                                "Содержимое",
                                doc[:2000],
                                height=150,
                                disabled=True,
                                key=f"search_doc_{i}",
                            )


def _render_indexed_data(api: ApiClient, admin_token: str) -> None:
    st.subheader("Проиндексированные данные")

    tab1, tab2 = st.tabs(["Отчёты", "Документы"])

    with tab1:
        if st.button("Загрузить список отчётов", key="load_reports"):
            result = api.get("/rag/reports", admin_token=admin_token)
            if result is not None:
                items = result.get("items", [])
                total = result.get("total", 0)
                st.write(f"Всего проиндексировано: **{total}** отчётов")

                for item in items:
                    meta = item.get("metadata", {})
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.write(f"**{meta.get('client_name', 'N/A')}** (ИНН: {meta.get('inn', 'N/A')})")
                    with col2:
                        risk = meta.get("risk_score", "N/A")
                        st.write(f"Риск: {risk}")
                    with col3:
                        report_id = item.get("id", "").replace("report:", "")
                        if st.button("Удалить", key=f"del_report_{report_id}"):
                            api.delete(
                                f"/rag/reports/{report_id}",
                                admin_token=admin_token,
                            )
                            st.rerun()

    with tab2:
        if st.button("Загрузить список документов", key="load_docs"):
            result = api.get("/rag/documents", admin_token=admin_token)
            if result is not None:
                items = result.get("items", [])
                total = result.get("total", 0)
                st.write(f"Всего загружено: **{total}** документов")

                for item in items:
                    meta = item.get("metadata", {})
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.write(f"**{meta.get('filename', 'N/A')}**")
                    with col2:
                        chunks = meta.get("total_chunks", item.get("chunk_count", "N/A"))
                        st.write(f"Чанков: {chunks}")
                    with col3:
                        doc_id = item.get("id", "")
                        if st.button("Удалить", key=f"del_doc_{doc_id}"):
                            api.delete(
                                f"/rag/documents/{doc_id}",
                                admin_token=admin_token,
                            )
                            st.rerun()


def _render_stats(api: ApiClient, admin_token: str) -> None:
    st.subheader("Статистика RAG")

    if st.button("Обновить статистику", key="refresh_stats"):
        result = api.get("/rag/stats", admin_token=admin_token)
        if result is not None:
            chroma = result.get("chroma", {})
            embedding = result.get("embedding", {})

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Отчётов", chroma.get("reports_count", 0))
            with col2:
                st.metric("Чанков документов", chroma.get("documents_chunks_count", 0))
            with col3:
                model_loaded = embedding.get("model_loaded", False)
                st.metric("Модель", "Загружена" if model_loaded else "Не загружена")

            if embedding.get("model_name"):
                st.info(f"Embedding модель: {embedding['model_name']}")
