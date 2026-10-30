"""Offline transport-budget tests; fixtures are not model inference or real videos."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from aniflow.studio import comfy_provider
from aniflow.studio.comfy_provider import ComfyProvider, DownloadBudgetError

HISTORY = {"outputs": {"16": {"videos": [
    {"filename": "source.mp4", "subfolder": "aniflow", "type": "output"}]}}}
KEY = "offline-budget-request-001"


@pytest.fixture
def verification(monkeypatch):
    metadata = {"offline_transport_fixture_only": True}
    monkeypatch.setattr(comfy_provider, "verify_mp4", lambda *_: dict(metadata))
    return metadata


def options(tmp_path, limit=64):
    return {"max_download_bytes": limit, "budget_path": tmp_path / "download-budget.json",
            "request_key": KEY}


def test_budget_is_reserved_before_get_and_verified_source_is_reused_after_restart(tmp_path, verification):
    seen, raw = [], b"transport fixture, not a video"

    def upstream(request):
        state = json.loads((tmp_path / "download-budget.json").read_text())
        assert state["phase"] == "reserved" and state["reserved_bytes"] == 64
        seen.append(request.method)
        return httpx.Response(200, content=raw)

    path = tmp_path / "source.mp4"
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(upstream))
    first = provider.download(HISTORY, path, **options(tmp_path))
    provider.client.close()
    def forbidden(_request):
        raise AssertionError("A verified local source must not be downloaded again")
    second = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(forbidden)).download(
        HISTORY, path, **options(tmp_path))
    assert first == second == (hashlib.sha256(raw).hexdigest(), len(raw), verification)
    assert seen == ["GET"] and path.read_bytes() == raw
    receipt = json.loads((tmp_path / "download-budget.json").read_text())
    assert receipt["phase"] == "complete" and receipt["attempts"] == 1
    assert receipt["binding"]["data_dir"] == str(tmp_path.resolve())


def test_unknown_get_outcome_keeps_reservation_and_blocks_another_get_after_restart(tmp_path, verification):
    calls = []
    def outage(request):
        calls.append(request.method)
        raise httpx.ReadError("Synthetic accepted GET response loss")
    path = tmp_path / "source.mp4"
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(outage))
    with pytest.raises(httpx.ReadError):
        provider.download(HISTORY, path, **options(tmp_path))
    restarted = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(outage))
    with pytest.raises(DownloadBudgetError, match="unknown"):
        restarted.download(HISTORY, path, **options(tmp_path))
    state = json.loads((tmp_path / "download-budget.json").read_text())
    assert state["reserved_bytes"] == 64 and state["phase"] == "reserved"
    assert calls == ["GET"] and not path.exists()


@pytest.mark.parametrize("change", ["request", "artifact", "limit", "content"])
def test_binding_and_verified_source_cannot_be_replaced_to_obtain_another_get(tmp_path, verification, change):
    calls = []
    def upstream(request):
        calls.append(request.method)
        return httpx.Response(200, content=b"fixture")
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(upstream))
    path, kwargs = tmp_path / "source.mp4", options(tmp_path)
    provider.download(HISTORY, path, **kwargs)
    history = json.loads(json.dumps(HISTORY))
    if change == "request":
        kwargs["request_key"] = "different-request-002"
    elif change == "artifact":
        history["outputs"]["16"]["videos"][0]["filename"] = "different.mp4"
    elif change == "limit":
        kwargs["max_download_bytes"] = 128
    else:
        path.write_bytes(b"changed")
    with pytest.raises(DownloadBudgetError):
        provider.download(history, path, **kwargs)
    assert calls == ["GET"]


def test_oversized_declared_media_does_not_read_the_body_or_release_reservation(tmp_path, verification):
    consumed = []
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            consumed.append(True)
            yield b"x" * 65
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"Content-Length": "65"}, stream=Body())))
    with pytest.raises(DownloadBudgetError, match="limit"):
        provider.download(HISTORY, tmp_path / "source.mp4", **options(tmp_path))
    assert not consumed
    assert json.loads((tmp_path / "download-budget.json").read_text())["reserved_bytes"] == 64


def test_missing_length_reserves_maximum_and_rejects_a_body_over_the_limit(tmp_path, verification):
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 65
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(
        lambda _: httpx.Response(200, stream=Body())))
    with pytest.raises(DownloadBudgetError, match="limit"):
        provider.download(HISTORY, tmp_path / "source.mp4", **options(tmp_path))
    assert not (tmp_path / "source.mp4").exists()
    assert not (tmp_path / "source.mp4.partial").exists()


def test_verified_partial_is_recovered_locally_if_rename_was_interrupted(tmp_path, verification, monkeypatch):
    calls, blocked = [], {"once": True}
    def upstream(request):
        calls.append(request.method)
        return httpx.Response(200, content=b"verified transport fixture")
    original = Path.replace
    def interrupted(source, destination):
        if source.name == "source.mp4.partial" and blocked["once"]:
            blocked["once"] = False
            raise OSError("Synthetic rename interruption")
        return original(source, destination)
    monkeypatch.setattr(Path, "replace", interrupted)
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(upstream))
    path = tmp_path / "source.mp4"
    with pytest.raises(OSError):
        provider.download(HISTORY, path, **options(tmp_path))
    assert json.loads((tmp_path / "download-budget.json").read_text())["phase"] == "verified"
    assert path.with_suffix(".mp4.partial").exists()
    provider.download(HISTORY, path, **options(tmp_path))
    assert path.exists() and calls == ["GET"]


def test_default_provider_still_uses_legacy_download_without_a_budget_file(tmp_path, verification):
    provider = ComfyProvider("http://127.0.0.1:18188", httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"legacy fixture")))
    provider.download(HISTORY, tmp_path / "source.mp4")
    assert not (tmp_path / "download-budget.json").exists()
