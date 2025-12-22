from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# Ensure repo root is on sys.path so `import app.*` works when running from app/frontend.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.frontend.api_client import get_api_client
from app.frontend.router import TAB_BY_KEY, TAB_DEFS, enforce_access, set_tab
from app.frontend.tabs import analysis as tab_analysis
from app.frontend.tabs import data as tab_data
from app.frontend.tabs import docs as tab_docs
from app.frontend.tabs import utilities as tab_utilities


def _load_css() -> None:
    css_path = Path(__file__).resolve().parent / "assets" / "styles.css"
    try:
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    except Exception:
        # CSS is optional; UI should still work.
        pass


def _init_state() -> None:
    st.session_state.setdefault("admin_token", "")
    st.session_state.setdefault("is_admin", False)


def _apply_admin_token(token: str) -> None:
    expected = (os.getenv("ADMIN_TOKEN", "") or "").strip()
    token = (token or "").strip()

    st.session_state["admin_token"] = token
    st.session_state["is_admin"] = bool(expected and token and token == expected)


def _logout_admin() -> None:
    st.session_state["admin_token"] = ""
    st.session_state["is_admin"] = False


def _render_sidebar() -> None:
    current_tab = st.session_state.get("tab", "analysis")
    is_admin = bool(st.session_state.get("is_admin", False))

    with st.sidebar:
        st.title("Навигация")

        st.caption("Переключение вкладок — внутри одного файла (single-page).")

        for t in TAB_DEFS:
            if t.admin_only and not is_admin:
                continue
            btn_type = "primary" if t.key == current_tab else "secondary"
            if st.button(t.label, use_container_width=True, type=btn_type):
                set_tab(t.key)

        st.divider()
        st.subheader("Admin token")

        token_input = st.text_input(
            "Введите ADMIN_TOKEN",
            type="password",
            value=st.session_state.get("admin_token", ""),
            placeholder="••••••••",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Применить", use_container_width=True):
                _apply_admin_token(token_input)
                # If we were on an admin-only tab and token is wrong -> enforce redirect.
                enforce_access(is_admin=bool(st.session_state.get("is_admin", False)))
                st.rerun()
        with col2:
            if st.button("Выйти", use_container_width=True):
                _logout_admin()
                enforce_access(is_admin=False)
                st.rerun()

        if is_admin:
            st.success("Админ-режим включён")
        elif st.session_state.get("admin_token"):
            st.warning("Токен неверный")


def main() -> None:
    st.set_page_config(
        page_title="Система анализа контрагентов",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _load_css()
    _init_state()

    # Router sync + access control (also handles direct ?tab=utilities/docs).
    enforce_access(is_admin=bool(st.session_state.get("is_admin", False)))

    _render_sidebar()

    api = get_api_client()

    tab = st.session_state.get("tab", "analysis")
    tab_def = TAB_BY_KEY.get(tab)
    if not tab_def:
        set_tab("analysis")
        return

    if tab == "analysis":
        tab_analysis.render(api)
    elif tab == "data":
        tab_data.render(api)
    elif tab == "utilities":
        tab_utilities.render(api, admin_token=st.session_state.get("admin_token", ""))
    elif tab == "docs":
        tab_docs.render(api)
    else:
        set_tab("analysis")


if __name__ == "__main__":
    main()

