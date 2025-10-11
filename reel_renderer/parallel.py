"""Parallel FFmpeg rendering helpers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from moviepy.editor import AudioFileClip

logger = logging.getLogger("reel_renderer.parallel")


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    bg_color: str = "#000000"
    preset: str = "veryfast"
    crf: int = 23
    audio_bitrate: str = "128k"
    audio_sample_rate: int = 48000
    test_mode: bool = False
    quality: str = "final"


@dataclass
class SlideConfig:
    image_path: str
    audio_path: str
    duration: float
    motion: Optional[Dict[str, Any]] = None
    transform: Optional[Dict[str, Any]] = None
    index: int = 0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _parse_rgb_component(component: str) -> int:
    value = component.strip()
    if not value:
        return 0
    try:
        if value.endswith("%"):
            percent = float(value[:-1])
            return int(round(_clamp(percent, 0.0, 100.0) * 255 / 100))
        if "." in value:
            float_val = float(value)
            if 0.0 <= float_val <= 1.0:
                return int(round(_clamp(float_val, 0.0, 1.0) * 255))
            return int(round(_clamp(float_val, 0.0, 255.0)))
        return int(round(_clamp(float(value), 0.0, 255.0)))
    except ValueError:
        return 0


def _parse_alpha_component(component: str) -> int:
    value = component.strip()
    if not value:
        return 255
    try:
        if value.endswith("%"):
            percent = float(value[:-1])
            return int(round(_clamp(percent, 0.0, 100.0) * 255 / 100))
        float_val = float(value)
        if 0.0 <= float_val <= 1.0:
            return int(round(_clamp(float_val, 0.0, 1.0) * 255))
        return int(round(_clamp(float_val, 0.0, 255.0)))
    except ValueError:
        return 255


def _normalize_ffmpeg_color(color: str) -> str:
    if not color:
        return "black"

    candidate = color.strip()
    if not candidate:
        return "black"

    lowered = candidate.lower()
    if lowered == "transparent":
        return "0x00000000"

    if candidate.startswith("0x") or candidate.startswith("0X"):
        return candidate

    if candidate.startswith("#"):
        hex_value = candidate.lstrip("#")
        if len(hex_value) in {3, 4}:
            hex_value = "".join(ch * 2 for ch in hex_value)
        if len(hex_value) in {6, 8}:
            return f"0x{hex_value.upper()}"
        logger.warning(
            "Unsupported hex color length for FFmpeg background",
            extra={"color": candidate},
        )
        return "black"

    match = re.fullmatch(r"rgba?\(([^)]+)\)", candidate, flags=re.IGNORECASE)
    if match:
        parts = [part.strip() for part in match.group(1).split(",") if part.strip()]
        if len(parts) >= 3:
            r, g, b = (_parse_rgb_component(p) for p in parts[:3])
            a = _parse_alpha_component(parts[3]) if len(parts) >= 4 else 255
            if a == 255:
                return f"0x{r:02X}{g:02X}{b:02X}"
            return f"0x{r:02X}{g:02X}{b:02X}{a:02X}"
        logger.warning(
            "RGBA color string had insufficient components",
            extra={"color": candidate},
        )
        return "black"

    if re.fullmatch(r"[A-Za-z]+", candidate):
        return lowered

    logger.warning("Unknown background color format", extra={"color": candidate})
    return "black"


@lru_cache(maxsize=1)
def _get_ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY")
    if configured:
        if os.path.isfile(configured):
            return configured
        if shutil.which(configured):
            return configured
        logger.warning(
            "Configured FFMPEG_BINARY was not found on disk or PATH",
            extra={"value": configured},
        )

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "FFmpeg binary not found. Install ffmpeg or set FFMPEG_BINARY."
        ) from exc


async def _run_subprocess(
    cmd: List[str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, bytes, bytes]:
    if os.name == "nt":
        def _run_sync() -> subprocess.CompletedProcess[bytes]:
            kwargs: Dict[str, Any] = {
                "cwd": cwd,
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "check": False,
            }
            create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", None)
            if create_no_window is not None:
                kwargs["creationflags"] = create_no_window
            return subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]

        completed = await asyncio.to_thread(_run_sync)
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        return completed.returncode, stdout, stderr

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout or b"", stderr or b""


def _get_quality_resolution(width: int, height: int, quality: str) -> Tuple[int, int]:
    if quality == "final":
        return width, height

    aspect = width / height
    if aspect > 1:
        draft_height = 540
        draft_width = int(540 * aspect)
    else:
        draft_width = 540
        draft_height = int(540 / aspect)

    draft_width += draft_width % 2
    draft_height += draft_height % 2

    return draft_width, draft_height


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _parse_transition_spec(motion: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(motion, dict):
        return None

    transition = motion.get("transition")
    if not isinstance(transition, dict):
        return None

    transition_type = (transition.get("type") or "").strip().lower()
    if transition_type not in {"fade", "crossfade", "dissolve"}:
        return None

    try:
        duration = float(transition.get("duration", 0.0))
    except (TypeError, ValueError):
        return None

    if duration <= 0.0:
        return None

    return {"type": transition_type, "duration": duration}


async def _render_slide_ffmpeg(
    slide: SlideConfig,
    config: RenderConfig,
    output_path: str,
) -> bool:
    try:
        if not os.path.exists(slide.image_path):
            logger.error(
                "Image file not found for slide",
                extra={"slide_index": slide.index, "image_path": slide.image_path},
            )
            return False

        if not os.path.exists(slide.audio_path):
            logger.error(
                "Audio file not found for slide",
                extra={"slide_index": slide.index, "audio_path": slide.audio_path},
            )
            return False

        if slide.transform:
            logger.info(
                "Ignoring slide transform in parallel renderer",
                extra={"slide_index": slide.index},
            )

        render_width, render_height = _get_quality_resolution(
            config.width, config.height, config.quality
        )

        ffmpeg_bin = _get_ffmpeg_binary()
        bg_color = _normalize_ffmpeg_color(config.bg_color)

        if config.quality == "draft":
            preset = "ultrafast"
            crf = "28"
            tune_params: List[str] = []
        else:
            preset = config.preset
            crf = str(config.crf)
            tune_params = ["-tune", "stillimage"]

        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-i",
            slide.image_path,
            "-i",
            slide.audio_path,
            "-t",
            str(slide.duration),
            "-vf",
            f"scale={render_width}:{render_height}:force_original_aspect_ratio=decrease,"
            f"pad={render_width}:{render_height}:(ow-iw)/2:(oh-ih)/2:color={bg_color},"
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            *tune_params,
            "-r",
            str(config.fps),
            "-c:a",
            "aac",
            "-b:a",
            config.audio_bitrate,
            "-ar",
            str(config.audio_sample_rate),
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
        ]

        return_code, stdout, stderr = await _run_subprocess(cmd)

        if return_code != 0:
            error_msg = stderr.decode(errors="ignore") if stderr else "Unknown FFmpeg error"
            logger.error(
                "FFmpeg subprocess failed",
                extra={
                    "slide_index": slide.index,
                    "return_code": return_code,
                    "stderr": error_msg,
                },
            )
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception:  # pragma: no cover - logged below
        logger.exception("Error rendering slide", extra={"slide_index": slide.index})
        return False


async def render_slides_parallel(
    slides: List[SlideConfig],
    config: RenderConfig,
    work_dir: str,
    max_workers: int = 16,
) -> List[str]:
    os.makedirs(work_dir, exist_ok=True)
    output_paths = [os.path.join(work_dir, f"slide_{idx:03d}.mp4") for idx in range(len(slides))]

    semaphore = asyncio.Semaphore(max_workers)

    async def render_with_limit(slide: SlideConfig, output: str) -> bool:
        async with semaphore:
            return await _render_slide_ffmpeg(slide, config, output)

    tasks = [render_with_limit(slide, output) for slide, output in zip(slides, output_paths)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failed = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception) or result is False:
            failed.append(idx)

    if failed:
        raise RuntimeError(f"Failed to render {len(failed)} slides: {failed}")

    return output_paths


_TRANSITION_TYPE_MAP = {
    "fade": "fade",
    "crossfade": "fade",
    "dissolve": "dissolve",
}


async def concat_videos_ffmpeg(
    video_paths: List[str],
    output_path: str,
    work_dir: str,
    *,
    transitions: Optional[List[Optional[Dict[str, Any]]]] = None,
    durations: Optional[List[float]] = None,
    config: Optional[RenderConfig] = None,
) -> bool:
    try:
        ffmpeg_bin = _get_ffmpeg_binary()
        transitions = transitions or []
        has_transition = any(transitions)

        if not has_transition:
            concat_list = os.path.join(work_dir, "concat_list.txt")
            with open(concat_list, "w", encoding="utf-8") as file:
                for path in video_paths:
                    safe_path = path.replace("\\", "/").replace("'", "'\\''")
                    file.write(f"file '{safe_path}'\n")

            cmd = [
                ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c",
                "copy",
                output_path,
            ]

            return_code, stdout, stderr = await _run_subprocess(cmd)

            if return_code != 0:
                error_msg = stderr.decode(errors="ignore") if stderr else "Unknown FFmpeg error"
                logger.error(
                    "FFmpeg concat failed",
                    extra={"return_code": return_code, "stderr": error_msg},
                )
                return False

            return os.path.exists(output_path) and os.path.getsize(output_path) > 0

        logger.info(
            "Applying FFmpeg transitions",
            extra={
                "segments": len(video_paths),
                "transitions": sum(1 for item in transitions if item),
            },
        )

        if durations is None or len(durations) != len(video_paths):
            logger.error(
                "Durations required for transition concat",
                extra={
                    "durations_provided": durations is not None,
                    "durations_len": len(durations) if durations else None,
                    "segments": len(video_paths),
                },
            )
            return False

        cmd = [ffmpeg_bin, "-y"]
        for path in video_paths:
            cmd.extend(["-i", path])

        filter_parts: List[str] = []
        current_video_label = "[0:v]"
        current_audio_label = "[0:a]"
        current_duration = durations[0]

        for idx in range(1, len(video_paths)):
            boundary = transitions[idx - 1] if idx - 1 < len(transitions) else None
            next_video_label = f"[{idx}:v]"
            next_audio_label = f"[{idx}:a]"

            if boundary:
                transition_type = boundary.get("type", "fade")
                mapped = _TRANSITION_TYPE_MAP.get(transition_type, "fade")
                try:
                    duration = float(boundary.get("duration", 0.0))
                except (TypeError, ValueError):
                    duration = 0.0

                if duration <= 0.0:
                    boundary = None
                else:
                    duration = min(duration, current_duration, durations[idx])
                    offset = max(current_duration - duration, 0.0)
                    video_out = f"[vxf{idx}]"
                    audio_out = f"[axf{idx}]"
                    filter_parts.append(
                        f"{current_video_label}{next_video_label}"
                        f" xfade=transition={mapped}:duration={duration:.6f}:offset={offset:.6f} {video_out}"
                    )
                    filter_parts.append(
                        f"{current_audio_label}{next_audio_label}"
                        f" acrossfade=d={duration:.6f} {audio_out}"
                    )
                    current_video_label = video_out
                    current_audio_label = audio_out
                    current_duration = current_duration + durations[idx] - duration
                    continue

            video_out = f"[vcc{idx}]"
            audio_out = f"[acc{idx}]"
            filter_parts.append(
                f"{current_video_label}{next_video_label} concat=n=2:v=1:a=0 {video_out}"
            )
            filter_parts.append(
                f"{current_audio_label}{next_audio_label} concat=n=2:v=0:a=1 {audio_out}"
            )
            current_video_label = video_out
            current_audio_label = audio_out
            current_duration = current_duration + durations[idx]

        if not filter_parts:
            logger.error("Transition concat requested but no filters were generated")
            return False

        filter_complex = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex, "-map", current_video_label, "-map", current_audio_label])

        if config and config.quality == "draft":
            preset = "ultrafast"
            crf = "28"
        else:
            preset = config.preset if config else "veryfast"
            crf = str(config.crf if config else 23)

        audio_bitrate = config.audio_bitrate if config else "128k"
        audio_sample_rate = str(config.audio_sample_rate if config else 48000)

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                crf,
                "-c:a",
                "aac",
                "-b:a",
                audio_bitrate,
                "-ar",
                audio_sample_rate,
                "-movflags",
                "+faststart",
                output_path,
            ]
        )

        return_code, stdout, stderr = await _run_subprocess(cmd)

        if return_code != 0:
            error_msg = stderr.decode(errors="ignore") if stderr else "Unknown FFmpeg error"
            logger.error(
                "FFmpeg transition concat failed",
                extra={"return_code": return_code, "stderr": error_msg},
            )
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception:  # pragma: no cover
        logger.exception("Error concatenating videos")
        return False


async def render_video_parallel(
    images: List[str],
    audio_files: List[str],
    output_path: str,
    config: RenderConfig,
    motions: Optional[List[Optional[Dict[str, Any]]]] = None,
    transforms: Optional[List[Optional[Dict[str, Any]]]] = None,
    max_workers: int = 16,
) -> bool:
    work_dir = tempfile.mkdtemp(prefix="render_")

    try:
        durations = []
        for audio_path in audio_files:
            with AudioFileClip(audio_path) as clip:
                durations.append(clip.duration)

        slides: List[SlideConfig] = []
        transition_specs: List[Optional[Dict[str, Any]]] = []
        for idx, (img, audio, duration) in enumerate(zip(images, audio_files, durations)):
            motion = motions[idx] if motions and idx < len(motions) else None
            transform = (
                transforms[idx]
                if transforms and idx < len(transforms)
                else None
            )
            slides.append(
                SlideConfig(
                    image_path=img,
                    audio_path=audio,
                    duration=duration,
                    motion=motion,
                    transform=transform,
                    index=idx,
                )
            )
            transition_specs.append(_parse_transition_spec(motion))

        logger.info(
            "Rendering slides in parallel",
            extra={"count": len(slides), "max_workers": max_workers},
        )
        slide_videos = await render_slides_parallel(slides, config, work_dir, max_workers)

        boundary_transitions: List[Optional[Dict[str, Any]]] = []
        for idx in range(len(slides) - 1):
            chosen = transition_specs[idx]
            if not chosen:
                chosen = transition_specs[idx + 1] if idx + 1 < len(transition_specs) else None

            if chosen:
                duration = min(
                    float(chosen.get("duration", 0.0)),
                    durations[idx],
                    durations[idx + 1],
                )
                if duration > 0.0:
                    boundary_transitions.append(
                        {
                            "type": chosen.get("type", "fade"),
                            "duration": duration,
                        }
                    )
                    continue

            boundary_transitions.append(None)

        logger.info(
            "Concatenating slide segments",
            extra={"count": len(slide_videos)},
        )
        success = await concat_videos_ffmpeg(
            slide_videos,
            output_path,
            work_dir,
            transitions=boundary_transitions,
            durations=durations,
            config=config,
        )

        return success

    finally:
        with contextlib.suppress(Exception):
            shutil.rmtree(work_dir)


async def assemble_video_with_audio_parallel(
    images: List[str],
    audio_files: List[str],
    width: int,
    height: int,
    fps: int,
    bg_color: str,
    output_path: str,
    motions: Optional[List[Optional[Dict[str, Any]]]] = None,
    transforms: Optional[List[Optional[Dict[str, Any]]]] = None,
    *,
    test_mode: bool = False,
    max_workers: int = 16,
    quality: str = "final",
) -> bool:
    config = RenderConfig(
        width=width,
        height=height,
        fps=fps,
        bg_color=bg_color,
        test_mode=test_mode,
        quality=quality,
    )

    return await render_video_parallel(
        images=images,
        audio_files=audio_files,
        output_path=output_path,
        config=config,
        motions=motions,
        transforms=transforms,
        max_workers=max_workers,
    )
