from __future__ import annotations

from pathlib import Path

import httpx


async def download_file(url: str, destination: Path, timeout_seconds: float = 180.0) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
    return destination
