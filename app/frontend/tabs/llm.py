"""
LLM Access tab for direct LLM interaction with webhook callback support.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.ui import info_box, render_payload, section_header

# Provider options with display names
LLM_PROVIDERS: List[tuple[str, str]] = [
    ("OpenRouter (Claude 3.5 Sonnet)", "openrouter"),
    ("HuggingFace (Llama 3.1 70B)", "huggingface"),
    ("GigaChat (Sber)", "gigachat"),
    ("YandexGPT", "yandexgpt"),
    ("OpenLlama (Internal)", "openllama"),
]


def _get_token() -> str:
    """Get admin token from session_state."""
    return st.session_state.get("admin_token", "") or ""


def render(api: ApiClient) -> None:
    """Render the LLM Access tab."""
    st.header("LLM Direct Access")

    info_box(
        "Send prompts directly to LLM providers with async webhook support. "
        "Requests are processed asynchronously and results are delivered to your callback URL."
    )

    section = st.selectbox(
        "Select Section",
        options=[
            "Async Request (Webhook)",
            "Provider Status",
            "Request History",
        ],
        index=0,
        key="llm_section",
    )

    st.divider()

    if section == "Async Request (Webhook)":
        _render_async_request(api)
    elif section == "Provider Status":
        _render_provider_status(api)
    elif section == "Request History":
        _render_request_history()


def _render_async_request(api: ApiClient) -> None:
    """Render the async LLM request form."""
    section_header("Async LLM Request", emoji="robot", help_text="Submit request and receive result via webhook")

    st.info(
        "This endpoint accepts your request immediately (202 Accepted) "
        "and sends the result to your callback URL when ready."
    )

    with st.form("async_llm_form"):
        # Provider selection
        provider_labels = [p[0] for p in LLM_PROVIDERS]
        provider_label = st.selectbox(
            "LLM Provider",
            options=provider_labels,
            index=0,
            key="llm_provider_select",
        )
        provider_value = next(p[1] for p in LLM_PROVIDERS if p[0] == provider_label)

        # Prompt inputs
        system_prompt = st.text_area(
            "System Prompt (optional)",
            placeholder="You are a helpful assistant...",
            height=100,
            key="llm_system_prompt",
        )

        prompt = st.text_area(
            "User Prompt",
            placeholder="Enter your question or task...",
            height=200,
            key="llm_user_prompt",
        )

        # Callback configuration
        st.subheader("Callback Configuration")
        callback_url = st.text_input(
            "Callback URL",
            placeholder="https://your-service.com/webhook/llm-response",
            help="URL where the LLM response will be sent via POST",
            key="llm_callback_url",
        )

        col1, col2 = st.columns(2)
        with col1:
            callback_auth_header = st.text_input(
                "Authorization Header (optional)",
                type="password",
                placeholder="Bearer token...",
                key="llm_callback_auth",
            )
        with col2:
            pass  # Reserved for future options

        # LLM Parameters
        st.subheader("LLM Parameters")
        col1, col2 = st.columns(2)
        with col1:
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=0.7,
                step=0.1,
                key="llm_temperature",
            )
        with col2:
            max_tokens = st.number_input(
                "Max Tokens",
                min_value=100,
                max_value=32000,
                value=4096,
                step=100,
                key="llm_max_tokens",
            )

        # Metadata
        metadata_str = st.text_input(
            "Request Metadata (JSON, optional)",
            placeholder='{"source": "streamlit", "user_id": "123"}',
            key="llm_metadata",
        )

        submit = st.form_submit_button("Submit Async Request", type="primary")

    if submit:
        # Validation
        if not prompt.strip():
            st.error("Prompt is required")
            return
        if not callback_url.strip():
            st.error("Callback URL is required")
            return

        # Parse metadata
        metadata = None
        if metadata_str.strip():
            try:
                metadata = json.loads(metadata_str)
            except json.JSONDecodeError:
                st.error("Invalid JSON in metadata field")
                return

        # Build payload
        payload: Dict[str, Any] = {
            "prompt": prompt.strip(),
            "provider": provider_value,
            "callback_url": callback_url.strip(),
            "temperature": temperature,
            "max_tokens": int(max_tokens),
        }

        if system_prompt.strip():
            payload["system_prompt"] = system_prompt.strip()

        if callback_auth_header.strip():
            payload["callback_headers"] = {
                "Authorization": callback_auth_header.strip()
            }

        if metadata:
            payload["request_metadata"] = metadata

        # Submit request
        with st.spinner("Submitting request..."):
            result = api.post(
                "/llm/async",
                json=payload,
                admin_token=_get_token(),
            )

        if result:
            if result.get("status") == "accepted":
                st.success(f"Request accepted! ID: {result.get('request_id')}")

                # Save to history
                if "llm_request_history" not in st.session_state:
                    st.session_state["llm_request_history"] = []

                st.session_state["llm_request_history"].append({
                    "request_id": result.get("request_id"),
                    "provider": provider_value,
                    "callback_url": callback_url,
                    "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                })
            else:
                st.error(f"Request failed: {result.get('error', 'Unknown error')}")

            render_payload(result, title="Response")


def _render_provider_status(api: ApiClient) -> None:
    """Render the provider status section."""
    section_header("LLM Provider Status", emoji="satellite_antenna", help_text="Check availability of providers")

    if st.button("Refresh Status", type="primary", key="btn_refresh_providers"):
        with st.spinner("Checking providers..."):
            result = api.get("/llm/providers", admin_token=_get_token())

        if result:
            st.session_state["llm_provider_status"] = result

    status = st.session_state.get("llm_provider_status", {})
    if status:
        providers = status.get("providers", [])
        provider_status = status.get("status", {})

        if providers:
            cols = st.columns(len(providers))
            for idx, provider in enumerate(providers):
                with cols[idx]:
                    is_available = provider_status.get(provider, False)
                    if is_available:
                        st.metric(
                            provider.upper(),
                            "Available",
                            delta="OK",
                            delta_color="normal",
                        )
                    else:
                        st.metric(
                            provider.upper(),
                            "Unavailable",
                            delta="X",
                            delta_color="inverse",
                        )


def _render_request_history() -> None:
    """Render the request history section."""
    section_header("Request History", emoji="scroll", help_text="Recent requests from this session")

    history = st.session_state.get("llm_request_history", [])

    if not history:
        st.info("No requests submitted yet in this session")
        return

    # Clear history button
    if st.button("Clear History", key="btn_clear_llm_history"):
        st.session_state["llm_request_history"] = []
        st.rerun()

    # Show last 10 requests in reverse order
    for item in reversed(history[-10:]):
        with st.expander(f"{item['request_id'][:20]}... - {item['provider']}"):
            st.write(f"**Provider:** {item['provider']}")
            st.write(f"**Callback:** {item['callback_url']}")
            st.write(f"**Prompt:** {item['prompt_preview']}")


__all__ = ["render"]
