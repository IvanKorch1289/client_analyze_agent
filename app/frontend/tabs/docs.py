from __future__ import annotations

import pathlib

import streamlit as st

from app.frontend.api_client import ApiClient


def render(api: ApiClient) -> None:
    st.header("Документация (admin)")

    st.subheader("Ссылки")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("OpenAPI docs (Swagger)", api.url("/docs"))
        st.link_button("OpenAPI JSON", api.url("/openapi.json"))
    with c2:
        st.link_button("AsyncAPI HTML", api.url("/utility/asyncapi"))
        st.link_button("AsyncAPI JSON", api.url("/utility/asyncapi.json"))

    st.divider()
    st.subheader("Описание проекта")

    readme_path = pathlib.Path(__file__).resolve().parents[3] / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
    except Exception as e:
        st.error(f"Не удалось прочитать README.md: {e}")
        return

    st.markdown(text)

