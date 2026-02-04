from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
import streamlit as st


def _normalize_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        base_url = "http://localhost:8000/api/v1"
    return base_url.rstrip("/")


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"status": "error", "message": resp.text}


@dataclass(frozen=True)
class ApiClient:
    base_url: str
    timeout_seconds: int = 120  # Увеличено с 30 до 120 секунд для анализа клиентов

    @property
    def origin(self) -> str:
        """
        Origin of API_BASE_URL, e.g. http://localhost:8000
        """
        p = urlparse(self.base_url)
        return f"{p.scheme}://{p.netloc}"

    def url(self, path: str) -> str:
        """
        Build URL relative to API base (which already includes /api/v1).
        Examples:
        - url("/utility/health") -> http://host:8000/api/v1/utility/health
        - url("utility/health")  -> http://host:8000/api/v1/utility/health
        """
        if not path:
            return self.base_url
        path = str(path)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def absolute_url(self, path: str) -> str:
        """
        Build absolute URL from an absolute path (rooted at origin).
        This is useful for backend-provided download_url like "/api/v1/...".
        """
        if not path:
            return self.origin
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.origin + path

    def _headers(self, *, admin_token: Optional[str] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        token = (admin_token or "").strip()
        if token:
            headers["X-Auth-Token"] = token
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        admin_token: Optional[str] = None,
    ) -> Any:
        url = self.url(path)
        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                headers=self._headers(admin_token=admin_token),
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.Timeout:
            st.error(f"Таймаут запроса к API: {method.upper()} {url}")
            return None
        except Exception as e:
            st.error(f"Ошибка подключения к API: {e}")
            return None

        if 200 <= resp.status_code < 300:
            # Some endpoints return FileResponse / plain text; try JSON first.
            try:
                return resp.json()
            except Exception:
                return resp.text

        rid = resp.headers.get("X-Request-ID") or resp.headers.get("x-request-id")
        details = _safe_json(resp)
        if rid:
            st.error(f"Ошибка API: HTTP {resp.status_code} (request_id={rid})")
        else:
            st.error(f"Ошибка API: HTTP {resp.status_code}")
        st.caption(details)
        return None

    def get(
        self,
        path: str,
        params: Optional[dict] = None,
        *,
        admin_token: Optional[str] = None,
    ) -> Any:
        return self._request("GET", path, params=params, admin_token=admin_token)

    def post(
        self,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        *,
        admin_token: Optional[str] = None,
    ) -> Any:
        return self._request("POST", path, params=params, json=json, admin_token=admin_token)

    def delete(
        self,
        path: str,
        params: Optional[dict] = None,
        *,
        admin_token: Optional[str] = None,
    ) -> Any:
        return self._request("DELETE", path, params=params, admin_token=admin_token)

    def upload_file(
        self,
        path: str,
        files: dict,
        *,
        admin_token: Optional[str] = None,
    ) -> Any:
        """Upload a file via multipart/form-data."""
        url = self.url(path)
        headers = self._headers(admin_token=admin_token)
        # Remove Accept: application/json for multipart — let requests set Content-Type
        headers.pop("Accept", None)
        try:
            resp = requests.post(
                url=url,
                files=files,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.Timeout:
            st.error(f"Таймаут загрузки: POST {url}")
            return None
        except Exception as e:
            st.error(f"Ошибка загрузки: {e}")
            return None

        if 200 <= resp.status_code < 300:
            try:
                return resp.json()
            except Exception:
                return resp.text

        details = _safe_json(resp)
        st.error(f"Ошибка загрузки: HTTP {resp.status_code}")
        st.caption(details)
        return None


def get_api_client() -> ApiClient:
    from app.config.settings import settings as _cfg

    fe = _cfg.frontend
    base_url = _normalize_base_url(fe.base_url)
    return ApiClient(base_url=base_url, timeout_seconds=fe.timeout_seconds)
