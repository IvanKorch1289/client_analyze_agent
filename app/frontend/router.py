from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import streamlit as st


@dataclass(frozen=True)
class TabDef:
    key: str
    label: str
    admin_only: bool = False


TABS = ["Анализ клиента", "Внешние данные", "Утилиты", "Документация"]

TAB_DEFS: List[TabDef] = [
    TabDef(key="analysis", label="Анализ клиента", admin_only=False),
    TabDef(key="data", label="Внешние данные", admin_only=False),
    TabDef(key="utilities", label="Утилиты", admin_only=True),
    TabDef(key="docs", label="Документация", admin_only=True),
]

TAB_BY_KEY: Dict[str, TabDef] = {t.key: t for t in TAB_DEFS}
TAB_KEY_BY_LABEL: Dict[str, str] = {t.label.lower(): t.key for t in TAB_DEFS}


def _get_query_tab() -> Optional[str]:
    # Streamlit >= 1.30
    try:
        val = st.query_params.get("tab")
        if isinstance(val, list):
            return (val[0] or "").strip() or None
        return (val or "").strip() or None
    except Exception:
        # Legacy fallback
        try:
            qp = st.experimental_get_query_params()
            vals = qp.get("tab") or []
            return (vals[0] or "").strip() if vals else None
        except Exception:
            return None


def _set_query_tab(tab_key: str) -> None:
    try:
        st.query_params["tab"] = tab_key
    except Exception:
        st.experimental_set_query_params(tab=tab_key)


def normalize_tab(tab: Optional[str]) -> Optional[str]:
    if not tab:
        return None
    raw = str(tab).strip()
    if not raw:
        return None

    # Accept keys
    if raw in TAB_BY_KEY:
        return raw

    # Accept common aliases
    aliases = {
        "analysis": "analysis",
        "client": "analysis",
        "home": "analysis",
        "main": "analysis",
        "data": "data",
        "external": "data",
        "utilities": "utilities",
        "utils": "utilities",
        "admin": "utilities",
        "docs": "docs",
        "documentation": "docs",
    }
    if raw.lower() in aliases:
        return aliases[raw.lower()]

    # Accept labels (including Russian)
    label_key = TAB_KEY_BY_LABEL.get(raw.lower())
    if label_key:
        return label_key

    return None


def init_router_state() -> None:
    if "tab" not in st.session_state:
        st.session_state["tab"] = "analysis"


def set_tab(tab_key: str, *, rerun: bool = True) -> None:
    st.session_state["tab"] = tab_key
    _set_query_tab(tab_key)
    if rerun:
        st.rerun()


def enforce_access(is_admin: bool) -> None:
    """
    Sync tab with query params and enforce admin-only access.
    If invalid/forbidden tab is detected -> redirect to analysis (with rerun).
    """
    init_router_state()

    desired = normalize_tab(_get_query_tab()) or st.session_state.get("tab")
    desired = normalize_tab(desired) or "analysis"

    tab_def = TAB_BY_KEY.get(desired)
    if not tab_def:
        set_tab("analysis")
        return

    if tab_def.admin_only and not is_admin:
        set_tab("analysis")
        return

    # Canonicalize + keep in sync
    if st.session_state.get("tab") != desired:
        st.session_state["tab"] = desired
    _set_query_tab(desired)
