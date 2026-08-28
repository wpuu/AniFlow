import pytest

from aniflow.agnes.key_pool import KeyPool


@pytest.mark.asyncio
async def test_key_pool_round_robin_across_accounts():
    pool = KeyPool(["k1", "k2", "k3"])
    slots = [await pool.next() for _ in range(5)]
    assert [slot.api_key for slot in slots] == ["k1", "k2", "k3", "k1", "k2"]
    assert [slot.label for slot in slots[:3]] == ["account-1", "account-2", "account-3"]


def test_key_pool_requires_at_least_one_key():
    with pytest.raises(ValueError):
        KeyPool([])
