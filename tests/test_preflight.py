from __future__ import annotations

import pytest

from aniflow.config import Settings
from aniflow.preflight import PreflightReport, run_preflight


class FakeAgnesHttp:
    async def request_json(self, method, url, *, api_key, json=None, params=None):
        assert method == "POST"
        assert url.endswith("/v1/chat/completions")
        assert api_key in {"key-a", "key-b"}
        return {"choices": [{"message": {"content": "OK"}}]}


class FakeMediaStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def upload(self, local_path, object_key: str) -> str:
        url = f"https://media.example/{object_key}"
        self.objects[url] = local_path.read_bytes()
        return url

    async def delete(self, object_key: str) -> None:
        url = f"https://media.example/{object_key}"
        self.objects.pop(url, None)
        self.deleted.append(object_key)


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakePublicClient:
    def __init__(self, objects: dict[str, bytes], *args, **kwargs) -> None:
        self.objects = objects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str) -> FakeResponse:
        return FakeResponse(self.objects[url])


@pytest.mark.asyncio
async def test_preflight_checks_all_accounts_and_public_media(monkeypatch):
    settings = Settings(
        agnes_api_keys="key-a,key-b",
        s3_endpoint_url="https://s3.example",
        s3_access_key_id="id",
        s3_secret_access_key="secret",
        s3_bucket="bucket",
        s3_public_base_url="https://media.example",
    )
    store = FakeMediaStore()
    monkeypatch.setattr(
        "aniflow.preflight.httpx.AsyncClient",
        lambda *args, **kwargs: FakePublicClient(store.objects),
    )

    report = await run_preflight(
        settings=settings,
        http=FakeAgnesHttp(),
        media_store=store,
    )

    assert report.ok is True
    assert [item.account_label for item in report.agnes_accounts] == ["account-1", "account-2"]
    assert all(item.ok for item in report.agnes_accounts)
    assert report.media_upload_ok is True
    assert report.media_public_read_ok is True
    assert report.media_delete_ok is True
    assert len(store.deleted) == 1
    assert store.objects == {}


def test_preflight_report_requires_every_gate():
    report = PreflightReport(
        agnes_accounts=[],
        media_upload_ok=True,
        media_public_read_ok=True,
        media_delete_ok=True,
    )
    assert report.ok is False
