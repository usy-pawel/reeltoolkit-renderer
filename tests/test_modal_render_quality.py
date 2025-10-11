from __future__ import annotations

import base64
import io
import types
import zipfile
from pathlib import Path

import pytest

import modal_app
from reel_renderer import pipeline as renderer_pipeline
from reel_renderer.models import (
    Dimensions,
    RenderJobSpec,
    RenderOptions,
    SlideSpec,
    TransformSpec,
)


def _make_bundle() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("slide_000.png", b"image-bytes")
        archive.writestr("slide_000.mp3", b"audio-bytes")
        archive.writestr("karaoke.ass", "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Sample\n")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


@pytest.mark.parametrize(
    ("quality", "expected_width"),
    [("final", 1080), ("draft", 360)],
)
def test_render_impl_respects_quality_downscale(monkeypatch: pytest.MonkeyPatch, quality: str, expected_width: int) -> None:
    bundle_b64 = _make_bundle()
    captured_dims: dict[str, tuple[int, int]] = {}

    async def fake_render(spec, bundle_path, output_path, **_kwargs):
        captured_dims["dims"] = (spec.dimensions.width, spec.dimensions.height)
        Path(output_path).write_bytes(b"video-bytes")
        return Path(output_path)

    monkeypatch.setattr(renderer_pipeline, "render_reel", fake_render)
    monkeypatch.setattr(modal_app, "_log_gpu_info", lambda *_, **__: None)
    monkeypatch.setattr(
        modal_app.subprocess,
        "run",
        lambda *_, **__: types.SimpleNamespace(stdout="h264_nvenc", returncode=0, stderr=""),
    )
    monkeypatch.setattr(modal_app, "_estimate_render_cost", lambda *_, **__: {"cost_usd": None})

    gpu_preset = "L4" if quality == "draft" else "L40S"

    spec_dict = {
        "job_id": "test-job",
        "output_name": "out.mp4",
        "dimensions": {"width": 1080, "height": 1920, "fps": 30},
        "background_color": "#000000",
        "render": {"use_parallel": True, "quality": quality, "gpu_preset": gpu_preset},
        "slides": [
            {"image": "slide_000.png", "audio": "slide_000.mp3", "subtitle": True}
        ],
        "subtitle": {"format": "ass", "file": "karaoke.ass"},
    }

    result = modal_app._render_reel_impl(spec_dict, bundle_b64, gpu_name=gpu_preset)

    assert result["success"] is True
    assert captured_dims["dims"][0] == expected_width
    assert captured_dims["dims"][1] > 0


@pytest.mark.asyncio
async def test_render_pipeline_uses_moviepy_for_transform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "slide_000.png").write_bytes(b"image-bytes")
    (bundle_dir / "slide_000.mp3").write_bytes(b"audio-bytes")

    monkeypatch.setattr(
        renderer_pipeline,
        "_materialize_bundle",
        lambda bundle_path: (bundle_dir, None),
    )

    called = {"parallel": False, "video": False}

    async def fake_parallel(**_kwargs):
        called["parallel"] = True
        return True

    async def fake_video(
        *,
        images,
        audio_files,
        width,
        height,
        fps,
        bg_color,
        output_path,
        motions=None,
        transforms=None,
    ) -> None:
        called["video"] = True
        Path(output_path).write_bytes(b"video-bytes")

    monkeypatch.setattr(
        renderer_pipeline.parallel,
        "assemble_video_with_audio_parallel",
        fake_parallel,
    )
    monkeypatch.setattr(
        renderer_pipeline.video,
        "assemble_video_with_audio",
        fake_video,
    )

    spec = RenderJobSpec(
        job_id="job-transform",
        output_name="out.mp4",
        dimensions=Dimensions(width=1080, height=1920, fps=30),
        background_color="#000000",
        render=RenderOptions(use_parallel=True, quality="final"),
        slides=[
            SlideSpec(
                image="slide_000.png",
                audio="slide_000.mp3",
                transform=TransformSpec(scale=1.2, offset_x=20.0),
            )
        ],
        subtitle=None,
    )

    output_path = tmp_path / "final.mp4"
    await renderer_pipeline.render_reel(spec, str(bundle_dir), str(output_path))

    assert called["parallel"] is False
    assert called["video"] is True
    assert output_path.exists()
