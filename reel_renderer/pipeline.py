"""Main entrypoint for assembling reels from bundled assets."""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

from . import audio, parallel, video
from .models import RenderJobSpec


class RenderError(Exception):
    """Raised when the render pipeline encounters a fatal error."""


def _materialize_bundle(bundle_path: Path) -> tuple[Path, Optional[Path]]:
    if bundle_path.is_dir():
        return bundle_path, None
    if not bundle_path.exists():
        raise FileNotFoundError(f"bundle not found: {bundle_path}")

    extract_dir = Path(tempfile.mkdtemp(prefix="reel_bundle_"))
    with zipfile.ZipFile(bundle_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir, extract_dir


def _ensure_files(base: Path, paths: Iterable[str]) -> List[str]:
    abs_paths = []
    for rel in paths:
        candidate = base / rel
        if not candidate.exists():
            raise FileNotFoundError(f"asset missing in bundle: {rel}")
        abs_paths.append(str(candidate))
    return abs_paths


def _collect_motions(spec: RenderJobSpec) -> tuple[List[Optional[dict]], int]:
    motions: List[Optional[dict]] = []
    transitions = 0
    for slide in spec.slides:
        if slide.motion:
            payload = slide.motion.model_dump(exclude_none=True)
            if payload.get("transition"):
                transitions += 1
            motions.append(payload)
        else:
            motions.append(None)
    return motions, transitions


async def render_reel(
    spec: RenderJobSpec,
    bundle_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    max_workers: Optional[int] = None,
) -> Path:
    bundle = Path(bundle_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    assets_dir, cleanup_bundle = _materialize_bundle(bundle)

    work_dir = Path(tempfile.mkdtemp(prefix=f"render_{spec.job_id}_"))
    base_video = work_dir / "base.mp4"
    current_video = base_video

    try:
        images = _ensure_files(assets_dir, [slide.image for slide in spec.slides])
        audio_files = _ensure_files(assets_dir, [slide.audio for slide in spec.slides])
        motions, transitions = _collect_motions(spec)

        use_parallel = spec.render.use_parallel and transitions == 0
        if transitions and spec.render.use_parallel:
            # Fall back silently to MoviePy when transitions are needed
            use_parallel = False

        if use_parallel:
            if max_workers is not None:
                workers = max_workers
            else:
                env_workers = os.getenv("RENDER_MAX_WORKERS")
                try:
                    workers = int(env_workers) if env_workers else 16
                except (TypeError, ValueError):
                    workers = 16
            ok = await parallel.assemble_video_with_audio_parallel(
                images=images,
                audio_files=audio_files,
                width=spec.dimensions.width,
                height=spec.dimensions.height,
                fps=spec.dimensions.fps,
                bg_color=spec.background_color,
                output_path=str(base_video),
                motions=motions,
                max_workers=workers,
                quality=spec.render.quality,
            )
            if not ok:
                raise RenderError("parallel renderer failed")
        else:
            await video.assemble_video_with_audio(
                images=images,
                audio_files=audio_files,
                width=spec.dimensions.width,
                height=spec.dimensions.height,
                fps=spec.dimensions.fps,
                bg_color=spec.background_color,
                output_path=str(base_video),
                motions=motions,
            )

        if spec.subtitle:
            subtitle_path = _ensure_files(assets_dir, [spec.subtitle.file])[0]
            subbed_video = work_dir / "subbed.mp4"
            await video.burn_subtitles(str(current_video), subtitle_path, str(subbed_video))
            current_video = subbed_video

        if spec.ending_video:
            tail_path = _ensure_files(assets_dir, [spec.ending_video])[0]
            combined_video = work_dir / "combined.mp4"
            await video.append_video(str(current_video), tail_path, str(combined_video))
            current_video = combined_video

        if spec.background_music:
            music_path = _ensure_files(assets_dir, [spec.background_music.file])[0]
            mixed_video = work_dir / "mixed.mp4"
            mute_ranges = None
            if spec.background_music.mute_ranges:
                mute_ranges = [(float(start), float(end)) for start, end in spec.background_music.mute_ranges]

            if mute_ranges:
                await audio.mix_background_music_masked(
                    str(current_video),
                    music_path,
                    str(mixed_video),
                    volume=spec.background_music.volume or 0.15,
                    duck=spec.background_music.duck or False,
                    mute_ranges=mute_ranges,
                )
            else:
                await audio.mix_background_music(
                    str(current_video),
                    music_path,
                    str(mixed_video),
                    volume=spec.background_music.volume or 0.15,
                    duck=spec.background_music.duck or False,
                )
            current_video = mixed_video

        shutil.copy2(current_video, output)
        return output

    finally:
        with contextlib.suppress(Exception):
            shutil.rmtree(work_dir)
        if cleanup_bundle is not None:
            with contextlib.suppress(Exception):
                shutil.rmtree(cleanup_bundle)
