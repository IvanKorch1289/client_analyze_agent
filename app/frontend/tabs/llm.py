"""
Вкладка доступа к LLM для прямого взаимодействия с поддержкой webhook callback.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st

from app.frontend.api_client import ApiClient
from app.frontend.lib.ui import get_admin_token as _get_token, info_box, render_payload, section_header

# Опции провайдеров с отображаемыми именами
LLM_PROVIDERS: List[tuple[str, str]] = [
    ("OpenRouter (Claude 3.5 Sonnet)", "openrouter"),
    ("HuggingFace (Llama 3.1 70B)", "huggingface"),
    ("GigaChat (Сбер)", "gigachat"),
    ("YandexGPT", "yandexgpt"),
    ("OpenLlama (Внутренний)", "openllama"),
]


def render(api: ApiClient) -> None:
    """Отрисовка вкладки доступа к LLM."""
    st.header("Прямой доступ к LLM")

    info_box(
        "Отправляйте промпты напрямую провайдерам LLM с поддержкой асинхронного webhook. "
        "Запросы обрабатываются асинхронно, результаты доставляются на ваш callback URL."
    )

    section = st.selectbox(
        "Выберите раздел",
        options=[
            "Асинхронный запрос (Webhook)",
            "Статус провайдеров",
            "История запросов",
        ],
        index=0,
        key="llm_section",
    )

    st.divider()

    if section == "Асинхронный запрос (Webhook)":
        _render_async_request(api)
    elif section == "Статус провайдеров":
        _render_provider_status(api)
    elif section == "История запросов":
        _render_request_history()


def _render_async_request(api: ApiClient) -> None:
    """Отрисовка формы асинхронного LLM запроса."""
    section_header(
        "Асинхронный LLM запрос",
        emoji="robot",
        help_text="Отправьте запрос и получите результат через webhook",
    )

    st.info(
        "Этот эндпоинт принимает ваш запрос немедленно (202 Accepted) "
        "и отправляет результат на ваш callback URL, когда он будет готов."
    )

    with st.form("async_llm_form"):
        # Выбор провайдера
        provider_labels = [p[0] for p in LLM_PROVIDERS]
        provider_label = st.selectbox(
            "LLM Провайдер",
            options=provider_labels,
            index=0,
            key="llm_provider_select",
        )
        provider_value = next(p[1] for p in LLM_PROVIDERS if p[0] == provider_label)

        # Поля промптов
        system_prompt = st.text_area(
            "Системный промпт (опционально)",
            placeholder="Ты полезный ассистент...",
            height=100,
            key="llm_system_prompt",
        )

        prompt = st.text_area(
            "Пользовательский промпт",
            placeholder="Введите ваш вопрос или задачу...",
            height=200,
            key="llm_user_prompt",
        )

        # Настройка callback
        st.subheader("Настройка Callback")
        callback_url = st.text_input(
            "URL обратного вызова",
            placeholder="https://your-service.com/webhook/llm-response",
            help="URL, на который будет отправлен ответ LLM через POST",
            key="llm_callback_url",
        )

        col1, col2 = st.columns(2)
        with col1:
            callback_auth_header = st.text_input(
                "Заголовок авторизации (опционально)",
                type="password",
                placeholder="Bearer token...",
                key="llm_callback_auth",
            )
        with col2:
            pass  # Зарезервировано для будущих опций

        # Параметры LLM
        st.subheader("Параметры LLM")
        col1, col2 = st.columns(2)
        with col1:
            temperature = st.slider(
                "Температура",
                min_value=0.0,
                max_value=2.0,
                value=0.7,
                step=0.1,
                key="llm_temperature",
            )
        with col2:
            max_tokens = st.number_input(
                "Максимум токенов",
                min_value=100,
                max_value=32000,
                value=4096,
                step=100,
                key="llm_max_tokens",
            )

        # Метаданные
        metadata_str = st.text_input(
            "Метаданные запроса (JSON, опционально)",
            placeholder='{"source": "streamlit", "user_id": "123"}',
            key="llm_metadata",
        )

        submit = st.form_submit_button("Отправить асинхронный запрос", type="primary")

    if submit:
        # Валидация
        if not prompt.strip():
            st.error("Промпт обязателен")
            return
        if not callback_url.strip():
            st.error("Callback URL обязателен")
            return

        # Парсинг метаданных
        metadata = None
        if metadata_str.strip():
            try:
                metadata = json.loads(metadata_str)
            except json.JSONDecodeError:
                st.error("Невалидный JSON в поле метаданных")
                return

        # Формирование payload
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
            payload["callback_headers"] = {"Authorization": callback_auth_header.strip()}

        if metadata:
            payload["request_metadata"] = metadata

        # Отправка запроса
        with st.spinner("Отправка запроса..."):
            result = api.post(
                "/llm/async",
                json=payload,
                admin_token=_get_token(),
            )

        if result:
            if result.get("status") == "accepted":
                st.success(f"Запрос принят! ID: {result.get('request_id')}")

                # Сохранение в историю
                if "llm_request_history" not in st.session_state:
                    st.session_state["llm_request_history"] = []

                st.session_state["llm_request_history"].append(
                    {
                        "request_id": result.get("request_id"),
                        "provider": provider_value,
                        "callback_url": callback_url,
                        "prompt_preview": (prompt[:100] + "..." if len(prompt) > 100 else prompt),
                    }
                )
            else:
                st.error(f"Ошибка запроса: {result.get('error', 'Неизвестная ошибка')}")

            render_payload(result, title="Ответ")


def _render_provider_status(api: ApiClient) -> None:
    """Отрисовка раздела статуса провайдеров."""
    section_header(
        "Статус LLM провайдеров",
        emoji="satellite_antenna",
        help_text="Проверка доступности провайдеров",
    )

    if st.button("Обновить статус", type="primary", key="btn_refresh_providers"):
        with st.spinner("Проверка провайдеров..."):
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
                            "Доступен",
                            delta="OK",
                            delta_color="normal",
                        )
                    else:
                        st.metric(
                            provider.upper(),
                            "Недоступен",
                            delta="X",
                            delta_color="inverse",
                        )


def _render_request_history() -> None:
    """Отрисовка раздела истории запросов."""
    section_header("История запросов", emoji="scroll", help_text="Последние запросы этой сессии")

    history = st.session_state.get("llm_request_history", [])

    if not history:
        st.info("В этой сессии ещё нет отправленных запросов")
        return

    # Кнопка очистки истории
    if st.button("Очистить историю", key="btn_clear_llm_history"):
        st.session_state["llm_request_history"] = []
        st.rerun()

    # Показать последние 10 запросов в обратном порядке
    for item in reversed(history[-10:]):
        with st.expander(f"{item['request_id'][:20]}... - {item['provider']}"):
            st.write(f"**Провайдер:** {item['provider']}")
            st.write(f"**Callback:** {item['callback_url']}")
            st.write(f"**Промпт:** {item['prompt_preview']}")


__all__ = ["render"]
