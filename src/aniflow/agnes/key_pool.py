from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeySlot:
    index: int
    api_key: str

    @property
    def label(self) -> str:
        return f"account-{self.index + 1}"


class KeyPool:
    """Round-robin pool for API keys owned by separate Agnes accounts."""

    def __init__(self, api_keys: list[str]) -> None:
        cleaned = [key.strip() for key in api_keys if key.strip()]
        if not cleaned:
            raise ValueError("At least one Agnes API key is required")
        self._keys = tuple(cleaned)
        self._cursor = 0
        self._lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._keys)

    async def next(self) -> KeySlot:
        async with self._lock:
            index = self._cursor % len(self._keys)
            self._cursor += 1
        return KeySlot(index=index, api_key=self._keys[index])

    def all_slots(self) -> list[KeySlot]:
        return [KeySlot(index=index, api_key=key) for index, key in enumerate(self._keys)]
