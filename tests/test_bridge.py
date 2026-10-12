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
        "capcut_runner_ready": True,
        "capcut_ready": True,
        "frontend_ready": True,
        "capcut_model": "Seedream 5.0",
        "bridge": "aniflow-local",
    }


def test_bridge_reports_runner_ready_even_without_default_capcut_model() -> None:
    app = create_bridge_app(
        settings=Settings(capcut_runner_command='["python", "adapter.py"]'),
        media_store=FakeMediaStore(),
    )
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["capcut_runner_ready"] is True
    assert data["capcut_ready"] is False
    assert data["capcut_model"] is None


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


def test_agnes_image_without_s3_can_return_temporary_url(monkeypatch) -> None:
    import importlib

    module = importlib.import_module("aniflow.bridge.app")

    class FakeProvider:
        async def generate(self, **_kwargs) -> str:
            return "https://cdn.example.org/test-image.png?expires=short"

    monkeypatch.setattr(module, "AgnesImageProvider", lambda *_args: FakeProvider())
    settings = Settings(_env_file=None, s3_endpoint_url="", s3_access_key_id="",
                        s3_secret_access_key="", s3_bucket="", s3_public_base_url="")
    with TestClient(create_bridge_app(settings=settings)) as client:
        result = client.post("/api/images/generate", json={
            "provider": "agnes", "api_key": "FAKE_LOCAL_TEST_KEY",
            "prompt": "needle felt cat and bowl",
        })
        assert result.status_code == 200
        body = result.json()
        assert body["url"].startswith("https://cdn.example.org/")
        assert body["temporary"] is True
        assert "临时" in body["warning"]
        assert client.get("/api/health").json()["media_ready"] is False


def test_agnes_image_missing_key_reports_key_not_r2() -> None:
    settings = Settings(_env_file=None, s3_endpoint_url="", s3_access_key_id="",
                        s3_secret_access_key="", s3_bucket="", s3_public_base_url="")
    with TestClient(create_bridge_app(settings=settings)) as client:
        result = client.post("/api/images/generate", json={
            "provider": "agnes", "prompt": "needle felt cat",
        })
    assert result.status_code == 400
    assert "api_key" in result.json()["detail"]
    assert "S3" not in result.json()["detail"]


def test_agnes_image_refuses_private_upstream_image_link(monkeypatch) -> None:
    import importlib

    module = importlib.import_module("aniflow.bridge.app")

    class FakeProvider:
        async def generate(self, **_kwargs) -> str:
            return "http://127.0.0.1/private.png"

    monkeypatch.setattr(module, "AgnesImageProvider", lambda *_args: FakeProvider())
    settings = Settings(_env_file=None, s3_endpoint_url="", s3_access_key_id="",
                        s3_secret_access_key="", s3_bucket="", s3_public_base_url="")
    with TestClient(create_bridge_app(settings=settings)) as client:
        result = client.post("/api/images/generate", json={
            "provider": "agnes", "api_key": "FAKE_LOCAL_TEST_KEY",
            "prompt": "cat",
        })
    assert result.status_code == 502
    assert "S3" not in result.json()["detail"]


def test_version_api_reports_noncached_source_frontend(tmp_path: Path) -> None:
    frontend = tmp_path / "apps" / "grok-frontend" / "dist" / "index.html"
    frontend.parent.mkdir(parents=True)
    frontend.write_text("<html>AniFlow</html>", encoding="utf-8")
    app = create_bridge_app(settings=Settings(aniflow_frontend_index=str(frontend)))
    with TestClient(app) as client:
        response = client.get("/api/version")
        page = client.get("/")
    assert response.status_code == 200
    assert response.json()["source_commit"] is None
    assert response.json()["build_type"] == "source"
    assert response.json()["frontend_verified"] is True
    assert page.headers["cache-control"].startswith("no-store")


def test_version_api_hash_matches_bundled_html_and_detects_tampering(tmp_path: Path) -> None:
    import hashlib
    import json

    frontend = tmp_path / "apps" / "grok-frontend" / "dist" / "index.html"
    frontend.parent.mkdir(parents=True)
    frontend.write_text("<html>AniFlow</html>", encoding="utf-8")
    digest = hashlib.sha256(frontend.read_bytes()).hexdigest()
    manifest = tmp_path / "prebuilt_frontend.json"
    manifest.write_text(json.dumps({"source_commit": "a" * 40, "frontend_sha256": digest}))
    app = create_bridge_app(settings=Settings(aniflow_frontend_index=str(frontend)))
    with TestClient(app) as client:
        verified = client.get("/api/version").json()
        assert verified["source_commit"] == "a" * 40
        assert verified["frontend_verified"] is True
        assert verified["build_type"] == "prebuilt"
        frontend.write_text("<html>tampered</html>", encoding="utf-8")
        tampered = client.get("/api/version").json()
        assert tampered["frontend_verified"] is False


def test_missing_media_store_explains_local_images_not_video_require_r2() -> None:
    settings = Settings(
        _env_file=None, s3_endpoint_url="", s3_access_key_id="",
        s3_secret_access_key="", s3_bucket="", s3_public_base_url="",
    )
    with TestClient(create_bridge_app(settings=settings)) as client:
        result = client.post(
            "/api/media/upload",
            files={"file": ("test.png", _png_bytes(), "image/png")},
        )
    assert result.status_code == 422
    message = result.json()["detail"]
    assert "local image uploads" in message
    assert "text-to-video does not need S3/R2" in message
