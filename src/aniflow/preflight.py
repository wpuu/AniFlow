from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesHttpClient
from aniflow.config import Settings
from aniflow.media.store import PublicMediaStore


class AgnesAccountCheck(BaseModel):
    account_label: str
    ok: bool
    detail: str


class PreflightReport(BaseModel):
    agnes_accounts: list[AgnesAccountCheck] = Field(default_factory=list)
    media_upload_ok: bool = False
    media_public_read_ok: bool = False
    media_delete_ok: bool = False

    @property
    def ok(self) -> bool:
        return (
            bool(self.agnes_accounts)
            and all(item.ok for item in self.agnes_accounts)
            and self.media_upload_ok
            and self.media_public_read_ok
            and self.media_delete_ok
        )


async def _check_agnes_key(
    *,
    settings: Settings,
    http: AgnesHttpClient,
    api_key: str,
    account_index: int,
) -> AgnesAccountCheck:
    label = f"account-{account_index + 1}"
    try:
        data = await http.request_json(
            "POST",
            f"{settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json={
                "model": settings.agnes_text_model,
                "messages": [
                    {
                        "role": "user",
                        "content": "AniFlow connectivity probe. Reply exactly: OK",
                    }
                ],
                "temperature": 0,
                "max_tokens": 16,
            },
        )
        text = str(data["choices"][0]["message"]["content"]).strip()
        if not text:
            raise RuntimeError("empty assistant response")
        return AgnesAccountCheck(account_label=label, ok=True, detail="reachable")
    except Exception as exc:
        return AgnesAccountCheck(
            account_label=label,
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )


async def run_preflight(
    *,
    settings: Settings,
    http: AgnesHttpClient,
    media_store: PublicMediaStore,
) -> PreflightReport:
    report = PreflightReport()
    report.agnes_accounts = list(
        await asyncio.gather(
            *[
                _check_agnes_key(
                    settings=settings,
                    http=http,
                    api_key=api_key,
                    account_index=index,
                )
                for index, api_key in enumerate(settings.api_keys)
            ]
        )
    )

    probe_id = uuid.uuid4().hex
    object_key = f"aniflow/preflight/{probe_id}.txt"
    expected = f"aniflow-preflight:{probe_id}\n".encode()
    uploaded = False

    try:
        with tempfile.TemporaryDirectory(prefix="aniflow-preflight-") as tmp:
            local_path = Path(tmp) / "probe.txt"
            local_path.write_bytes(expected)
            public_url = await media_store.upload(local_path, object_key)
            uploaded = True
            report.media_upload_ok = True

            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as public_client:
                response = await public_client.get(public_url)
                response.raise_for_status()
                report.media_public_read_ok = response.content == expected
    except Exception:
        report.media_public_read_ok = False
    finally:
        if uploaded:
            try:
                await media_store.delete(object_key)
                report.media_delete_ok = True
            except Exception:
                report.media_delete_ok = False

    return report
