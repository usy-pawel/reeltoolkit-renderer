from __future__ import annotations

import pathlib
from typing import Dict

import pytest

from reel_renderer import parallel


class _DummyAudioClip:
    def __init__(self, duration: float) -> None:
        self.duration = duration

    def __enter__(self) -> "_DummyAudioClip":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _stub_audio_factory(durations: Dict[str, float]):
    def _factory(path: str) -> _DummyAudioClip:
        try:
            value = durations[path]
        except KeyError as exc:  # pragma: no cover - defensive, helps debugging
            raise AssertionError(f"Unexpected audio clip requested: {path}") from exc
        return _DummyAudioClip(value)

    return _factory


@pytest.mark.asyncio
async def test_parallel_renderer_applies_transition(monkeypatch, tmp_path: pathlib.Path):
    audio_durations = {
        "audio0.mp3": 2.0,
        "audio1.mp3": 3.0,
    }

    async def fake_render_slides(slides, config, work_dir, max_workers):  # noqa: ARG001
        assert len(slides) == 2
        return [str(tmp_path / "slide0.mp4"), str(tmp_path / "slide1.mp4")]

    captured = {}

    async def fake_concat(videos, output_path, work_dir, *, transitions, durations, config):  # noqa: ARG001
        captured["videos"] = list(videos)
        captured["output"] = output_path
        captured["transitions"] = transitions
        captured["durations"] = durations
        captured["config"] = config
        return True

    monkeypatch.setattr(parallel, "render_slides_parallel", fake_render_slides)
    monkeypatch.setattr(parallel, "concat_videos_ffmpeg", fake_concat)
    monkeypatch.setattr(parallel, "AudioFileClip", _stub_audio_factory(audio_durations))

    config = parallel.RenderConfig(width=1080, height=1920, fps=30, bg_color="#000000")
    output_path = tmp_path / "final.mp4"

    motions = [
        {"transition": {"type": "crossfade", "duration": 1.5}},
        None,
    ]

    result = await parallel.render_video_parallel(
        images=["image0.png", "image1.png"],
        audio_files=list(audio_durations.keys()),
        output_path=str(output_path),
        config=config,
        motions=motions,
        max_workers=4,
    )

    assert result is True
    assert captured["transitions"] == [
        {"type": "crossfade", "duration": pytest.approx(1.5)}
    ]
    assert captured["durations"] == [pytest.approx(2.0), pytest.approx(3.0)]


@pytest.mark.asyncio
async def test_parallel_renderer_respects_next_slide_transition(monkeypatch, tmp_path: pathlib.Path):
    audio_durations = {
        "clip0.mp3": 1.0,
        "clip1.mp3": 1.0,
    }

    async def fake_render_slides(slides, config, work_dir, max_workers):  # noqa: ARG001
        return [str(tmp_path / "s0.mp4"), str(tmp_path / "s1.mp4")]

    captured = {}

    async def fake_concat(videos, output_path, work_dir, *, transitions, durations, config):  # noqa: ARG001
        captured["transitions"] = transitions
        captured["durations"] = durations
        return True

    monkeypatch.setattr(parallel, "render_slides_parallel", fake_render_slides)
    monkeypatch.setattr(parallel, "concat_videos_ffmpeg", fake_concat)
    monkeypatch.setattr(parallel, "AudioFileClip", _stub_audio_factory(audio_durations))

    config = parallel.RenderConfig(width=720, height=1280, fps=25, bg_color="#FFFFFF")

    motions = [
        None,
        {"transition": {"type": "fade", "duration": 2.5}},
    ]

    result = await parallel.render_video_parallel(
        images=["img0.png", "img1.png"],
        audio_files=list(audio_durations.keys()),
        output_path=str(tmp_path / "out.mp4"),
        config=config,
        motions=motions,
        max_workers=2,
    )

    assert result is True
    assert captured["transitions"] == [
        {"type": "fade", "duration": pytest.approx(1.0)}
    ]
    assert captured["durations"] == [pytest.approx(1.0), pytest.approx(1.0)]