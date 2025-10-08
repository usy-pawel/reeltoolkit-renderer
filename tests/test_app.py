from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import renderer_service.app as renderer_app
from renderer_service.config import get_settings
from reel_renderer.models import RenderJobSpec


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure env-driven settings refresh between tests."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_health_endpoint():
    client = TestClient(renderer_app.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def _fake_render_async(_spec, _bundle_path, output_path, **_kwargs):
    """Async mock function that properly simulates render_reel behavior."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy")
    return path


@pytest.mark.asyncio
async def test_render_requires_auth(monkeypatch):
    monkeypatch.setenv("RENDER_AUTH_TOKEN", "secret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(renderer_app, "render_reel", _fake_render_async)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=renderer_app.app), base_url="http://test") as client:
        payload = {
            "job_id": "job-123",
            "output_name": "result.mp4",
            "dimensions": {"width": 1080, "height": 1920, "fps": 30},
            "background_color": "#000000",
            "render": {"use_parallel": False, "quality": "final"},
            "slides": [
                {"image": "slide_000.png", "audio": "slide_000.mp3"},
            ],
        }

        payload_json = json.dumps(payload)

        bundle_stream = io.BytesIO()
        with zipfile.ZipFile(bundle_stream, "w") as archive:
            archive.writestr("placeholder.txt", "noop")
        bundle_stream.seek(0)

        response = await client.post(
            "/render/reel",
            headers={"Authorization": "Bearer secret"},
            files={
                "payload": (None, payload_json),
                "bundle": ("bundle.zip", bundle_stream, "application/zip"),
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Render-Job-Id"] == "job-123"
        assert response.headers["Content-Type"] == "video/mp4"
        assert response.content == b"dummy"


@pytest.mark.asyncio
async def test_render_unauthorized(monkeypatch):
    monkeypatch.setenv("RENDER_AUTH_TOKEN", "secret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(renderer_app, "render_reel", _fake_render_async)
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=renderer_app.app), base_url="http://test") as client:
        payload = {
            "job_id": "job-unauth",
            "output_name": "result.mp4",
            "dimensions": {"width": 1080, "height": 1920, "fps": 30},
            "background_color": "#000000",
            "render": {"use_parallel": False, "quality": "final"},
            "slides": [
                {"image": "slide_000.png", "audio": "slide_000.mp3"},
            ],
        }

        payload_json = json.dumps(payload)
        bundle_stream = io.BytesIO()
        with zipfile.ZipFile(bundle_stream, "w") as archive:
            archive.writestr("placeholder.txt", "noop")
        bundle_stream.seek(0)

        response = await client.post(
            "/render/reel",
            files={
                "payload": (None, payload_json),
                "bundle": ("bundle.zip", bundle_stream, "application/zip"),
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing bearer token"


def test_render_options_gpu_preset_normalized():
    payload = {
        "job_id": "gpu-test",
        "output_name": "out.mp4",
        "dimensions": {"width": 1080, "height": 1920, "fps": 30},
        "background_color": "#000000",
        "render": {"use_parallel": False, "quality": "final", "gpu_preset": "l40s"},
        "slides": [
            {"image": "slide_0.png", "audio": "slide_0.mp3"},
        ],
    }

    spec = RenderJobSpec.model_validate(payload)

    assert spec.render.gpu_preset == "L40S"
