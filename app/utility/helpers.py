from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Optional typing only; avoids runtime dependency issues
    from starlette.requests import Request


def clean_xml_dict(data):
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            new_key = key
            if isinstance(key, str):
                new_key = key.lstrip("@#")
            cleaned[new_key] = clean_xml_dict(value)
        return cleaned
    elif isinstance(data, list):
        return [clean_xml_dict(item) for item in data]
    else:
        return data


def get_client_ip(request: "Request") -> str:
    """
    Extract client IP address from request.

    Used by SlowAPI limiter in scheduler routes.
    """
    # Prefer X-Forwarded-For (first IP in list)
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    except Exception:
        pass

    # Fallback: X-Real-IP
    try:
        x_real = request.headers.get("x-real-ip")
        if x_real:
            return x_real.strip()
    except Exception:
        pass

    # Final fallback: request.client.host
    try:
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass

    return "unknown"
