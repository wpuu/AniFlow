from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aniflow.bridge.app import create_bridge_app
from aniflow.config import Settings


class FakeMediaStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []

    async def upload(self, local_path: Path, object_key: str) -> str:
        self.uploads.append((local_path.read_bytes(), object_key))
        return f"https://media.example/{object_key}"


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"test-image"


def test_bridge_health_reports_media_capcut_and_frontend_state(tmp_path: Path) -> None:
    frontend = tmp_path / "index.html"
    frontend.write_text("<html><body>AniFlow</body></html>", encoding="utf-8")
    app = create_bridge_app(
        settings=Settings(
            capcut_seedream_model="Seedream 5.0",
            capcut_runner_command='["python", "adapter.py"]',
            aniflow_frontend_index=str(frontend),
        ),
        media_store=FakeMediaStore(),
    )
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "media_ready": True,
        "capcut_ready": True,
        "frontend_ready": True,
        "capcut_model": "Seedream 5.0",
        "bridge": "aniflow-local",
    }


def test_bridge_root_serves_built_single_file_frontend(tmp_path: Path) -> None:
    frontend = tmp_path / "index.html"
    frontend.write_text("<html><body>AniFlow UI</body></html>", encoding="utf-8")
    app = create_bridge_app(
        settings=Settings(aniflow_frontend_index=str(frontend)),
        media_store=FakeMediaStore(),
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AniFlow UI" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_bridge_root_explains_when_frontend_is_not_built(tmp_path: Path) -> None:
    missing = tmp_path / "missing.html"
    app = create_bridge_app(
        settings=Settings(aniflow_frontend_index=str(missing)),
        media_store=FakeMediaStore(),
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 503
    assert "frontend has not been built" in response.json()["detail"]


def test_bridge_upload_persists_supported_image() -> None:
    store = FakeMediaStore()
    app = create_bridge_app(settings=Settings(), media_store=store)
    client = TestClient(app)

    response = client.post(
        "/api/media/upload",
        files={"file": ("frame.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("https://media.example/aniflow/uploads/")
    assert data["object_key"].startswith("aniflow/uploads/")
    assert data["object_key"].endswith(".png")
    assert data["size_bytes"] == len(_png_bytes())
    assert store.uploads[0][0] == _png_bytes()


def test_bridge_upload_rejects_non_image_payload() -> None:
    app = create_bridge_app(settings=Settings(), media_store=FakeMediaStore())
    client = TestClient(app)

    response = client.post(
        "/api/media/upload",
        files={"file": ("bad.txt", b"not-an-image", "text/plain")},
    )

    assert response.status_code == 415
