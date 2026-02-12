from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, Optional, TypeVar

import streamlit as st

logger = logging.getLogger(__name__)

T = TypeVar("T")


@contextmanager
def safe_api_call(
    operation_name: str,
    *,
    show_error: bool = True,
    log_error: bool = True,
) -> Generator[None, None, None]:
    """
    Context manager for safely wrapping API calls with error handling.

    Usage:
        with safe_api_call("Загрузка данных"):
            result = api.get("/endpoint")

    Args:
        operation_name: Human-readable name of the operation for error messages
        show_error: Whether to display st.error() on failure
        log_error: Whether to log the error for debugging

    Yields:
        None - the wrapped code executes within the context

    On exception:
        - Logs the error if log_error=True
        - Shows user-friendly error via st.error() if show_error=True
        - Does not re-raise, allowing graceful degradation
    """
    try:
        yield
    except TimeoutError as e:
        error_msg = f"Превышено время ожидания: {operation_name}"
        if log_error:
            logger.error(f"Timeout in {operation_name}: {e}")
        if show_error:
            st.error(f"⏱️ {error_msg}. Попробуйте повторить позже.")
    except ConnectionError as e:
        error_msg = f"Ошибка соединения: {operation_name}"
        if log_error:
            logger.error(f"Connection error in {operation_name}: {e}")
        if show_error:
            st.error(f"🔌 {error_msg}. Проверьте подключение к сети.")
    except ValueError as e:
        error_msg = f"Некорректные данные: {operation_name}"
        if log_error:
            logger.error(f"Value error in {operation_name}: {e}")
        if show_error:
            st.error(f"⚠️ {error_msg}: {str(e)}")
    except Exception as e:
        error_msg = f"Ошибка при выполнении: {operation_name}"
        if log_error:
            logger.exception(f"Unexpected error in {operation_name}: {e}")
        if show_error:
            st.error(f"❌ {error_msg}. Обратитесь к администратору.")


def safe_api_call_decorator(
    operation_name: str,
    *,
    show_error: bool = True,
    log_error: bool = True,
    default: Any = None,
) -> Callable[[Callable[..., T]], Callable[..., Optional[T]]]:
    """
    Decorator version of safe_api_call for wrapping functions.

    Usage:
        @safe_api_call_decorator("Загрузка данных")
        def fetch_data():
            return api.get("/endpoint")

    Args:
        operation_name: Human-readable name of the operation
        show_error: Whether to display st.error() on failure
        log_error: Whether to log the error for debugging
        default: Default value to return on failure (default: None)

    Returns:
        Decorated function that handles exceptions gracefully
    """

    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except TimeoutError as e:
                if log_error:
                    logger.error(f"Timeout in {operation_name}: {e}")
                if show_error:
                    st.error(f"⏱️ Превышено время ожидания: {operation_name}. Попробуйте повторить позже.")
                return default
            except ConnectionError as e:
                if log_error:
                    logger.error(f"Connection error in {operation_name}: {e}")
                if show_error:
                    st.error(f"🔌 Ошибка соединения: {operation_name}. Проверьте подключение к сети.")
                return default
            except ValueError as e:
                if log_error:
                    logger.error(f"Value error in {operation_name}: {e}")
                if show_error:
                    st.error(f"⚠️ Некорректные данные: {operation_name}: {str(e)}")
                return default
            except Exception as e:
                if log_error:
                    logger.exception(f"Unexpected error in {operation_name}: {e}")
                if show_error:
                    st.error(f"❌ Ошибка при выполнении: {operation_name}. Обратитесь к администратору.")
                return default

        return wrapper

    return decorator


def section_header(
    title: str,
    *,
    emoji: str = "",
    help_text: Optional[str] = None,
) -> None:
    header = f"{emoji} {title}" if emoji else title
    if help_text:
        st.markdown(f"### {header}")
        st.caption(help_text)
    else:
        st.markdown(f"### {header}")


def info_box(message: str, *, emoji: str = "ℹ️") -> None:
    st.info(f"{emoji} {message}")


def render_payload(
    payload: Any,
    *,
    title: str = "Response",
    expanded: bool = False,
    show_status: bool = True,
) -> None:
    if payload is None:
        st.warning(f"⚠️ {title}: нет данных")
        return

    if isinstance(payload, dict):
        status = payload.get("status", "")
        if show_status and status:
            if status == "success":
                st.success(f"✅ {title}")
            elif status == "error":
                st.error(f"❌ {title}")
            else:
                st.info(f"ℹ️ {title}")

        with st.expander(f"📋 {title}", expanded=expanded):
            st.json(payload)
    elif isinstance(payload, str):
        with st.expander(f"📋 {title}", expanded=expanded):
            st.text(payload)
    else:
        with st.expander(f"📋 {title}", expanded=expanded):
            st.json(payload)


def render_metric_cards(
    metrics: Dict[str, Any],
    *,
    columns: int = 3,
) -> None:
    cols = st.columns(columns)
    for idx, (label, value) in enumerate(metrics.items()):
        with cols[idx % columns]:
            st.metric(label=label, value=str(value))


def confirm_action(
    key: str,
    label: str = "Confirm action",
) -> bool:
    return st.checkbox(label, value=False, key=key)


def get_admin_token() -> str:
    """Get admin token from session state (shared across all tabs)."""
    return st.session_state.get("admin_token", "") or ""


def inn_input(
    label: str = "ИНН",
    *,
    placeholder: str = "7707083893",
    max_chars: int = 12,
    key: str = "inn_input",
    help_text: str = "Введите ИНН компании (10 или 12 цифр)",
) -> str:
    """
    Reusable INN input widget with validation.

    Returns:
        Cleaned INN string (digits only) or empty string.
    """
    raw = st.text_input(
        label,
        placeholder=placeholder,
        max_chars=max_chars,
        key=key,
        help=help_text,
    )
    return (raw or "").strip()


def validate_inn_input(inn: str) -> bool:
    """Validate INN and show error if invalid. Returns True if valid."""
    if not inn:
        return False
    if not inn.isdigit() or len(inn) not in (10, 12):
        st.error("Введите корректный ИНН (10 или 12 цифр)")
        return False
    return True


def service_status_badge(status: str) -> None:
    """Display a colored status badge for a service."""
    badges = {
        "ready": ("✅", "success"),
        "error": ("❌", "error"),
        "not_configured": ("⚙️", "warning"),
        "degraded": ("⚠️", "warning"),
    }
    emoji, method = badges.get(status, ("❓", "info"))
    getattr(st, method)(f"{emoji} {status}")


def progress_with_status(
    steps: list[tuple[str, float]],
    current_step: int,
    estimated_seconds: Optional[int] = None,
) -> None:
    """
    Display a progress bar with status text and optional time estimate.

    Args:
        steps: List of (step_name, progress_fraction) tuples
        current_step: Index of the current step (0-based)
        estimated_seconds: Optional estimated time remaining in seconds
    """
    if not steps or current_step < 0:
        return

    step_name, progress = steps[min(current_step, len(steps) - 1)]

    st.progress(progress, text=step_name)

    if estimated_seconds is not None and estimated_seconds > 0:
        if estimated_seconds >= 60:
            minutes = estimated_seconds // 60
            seconds = estimated_seconds % 60
            time_text = f"~{minutes} мин {seconds} сек"
        else:
            time_text = f"~{estimated_seconds} сек"
        st.caption(f"⏱️ Примерное время: {time_text}")
