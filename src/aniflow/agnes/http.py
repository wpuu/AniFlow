from __future__ import annotations

import asyncio
from typing import Any

import httpx


class AgnesApiError(RuntimeError):
    pass


class AgnesHttpClient:
    """Small async HTTP wrapper with bounded retry/backoff.

    API keys are passed per request so one AniFlow process can use multiple
    independently owned Agnes accounts without exposing credentials in logs.
    The 360-second default follows Agnes Image 2.1 Flash guidance for complex
    image generation/editing requests; video generation itself is asynchronous.
    """

    def __init__(self, timeout: float = 360.0, max_attempts: int = 4) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        self._max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        api_key: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break

            if response.status_code == 429 or response.status_code >= 500:
                last_error = AgnesApiError(self._http_error_message(response))
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break

            if 400 <= response.status_code < 500:
                raise AgnesApiError(self._http_error_message(response))

            try:
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                raise AgnesApiError(self._http_error_message(response)) from exc
            except ValueError as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break

            if not isinstance(payload, dict):
                raise AgnesApiError(f"Unexpected Agnes response type: {type(payload)!r}")
            return payload

        raise AgnesApiError(f"Agnes API request failed after retries: {last_error}") from last_error

    @staticmethod
    def _http_error_message(response: httpx.Response) -> str:
        detail: str | None = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw = payload.get("detail") or payload.get("message") or payload.get("error")
                if isinstance(raw, dict):
                    raw = raw.get("message") or raw.get("detail") or str(raw)
                if raw is not None:
                    detail = str(raw)
        except ValueError:
            pass
        suffix = f": {detail}" if detail else ""
        return f"Agnes API HTTP {response.status_code}{suffix}"
