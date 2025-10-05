"""High-level MoviePy helpers used by the render pipeline."""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _compute_zoom_scales(
    base_scale: float, motion_type: Optional[str], amount: float
) -> Tuple[float, float]:
    amount = max(0.0, min(amount, 0.25))
    if amount <= 1e-6:
        return base_scale, base_scale

    effective = min(amount * 0.2, 0.05)
    minimum_factor = 0.7
    if base_scale <= 0:
        return 1.0, 1.0

    if motion_type == "zoom-in":
        start = base_scale * max(minimum_factor, 1.0 - effective)
        end = base_scale * max(minimum_factor, 1.0 - effective * 0.5)
        return start, end

    if motion_type == "zoom-out":
        start = base_scale * max(minimum_factor, 1.0 - effective * 0.5)
        end = base_scale * max(minimum_factor, 1.0 - effective)
        return start, end

    return base_scale, base_scale


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


def _compose_with_transitions(
    clips: List[CompositeVideoClip],
    transitions: List[Optional[Dict[str, Any]]],
) -> CompositeVideoClip:
    if not clips:
        raise ValueError("At least one clip is required")

    if len(clips) == 1:
        return clips[0]

    has_transitions = any(t for t in transitions[:-1])
    if not has_transitions:
        return concatenate_videoclips(clips, method="compose")

    timeline: List[CompositeVideoClip] = []
    current_end = 0.0

    for idx, clip in enumerate(clips):
        if idx == 0:
            clip_with_start = clip.set_start(0.0)
            timeline.append(clip_with_start)
            current_end = clip.duration
            continue

        transition_spec = None
        prev_spec = transitions[idx - 1] if idx - 1 < len(transitions) else None
        next_spec = transitions[idx] if idx < len(transitions) else None
        for candidate in (prev_spec, next_spec):
            if candidate:
                transition_spec = candidate
                break

        overlap = 0.0
        if transition_spec:
            overlap = min(
                transition_spec["duration"],
                clips[idx - 1].duration,
                clip.duration,
            )

        if overlap > 1e-3:
            prev_clip = timeline[-1]
            prev_start = getattr(prev_clip, "start", 0.0)
            timeline[-1] = prev_clip.crossfadeout(overlap).set_start(prev_start)

            start_time = max(0.0, current_end - overlap)
            clip_with_start = clip.crossfadein(overlap).set_start(start_time)
            current_end = max(current_end, start_time + clip.duration)
        else:
            start_time = current_end
            clip_with_start = clip.set_start(start_time)
            current_end = start_time + clip.duration

        timeline.append(clip_with_start)

    final = CompositeVideoClip(timeline, size=clips[0].size)
    return final.set_duration(current_end)


async def assemble_video_with_audio(
    images: List[str],
    audio_files: List[str],
    width: int,
    height: int,
    fps: int,
    bg_color: str,
    output_path: str,
    motions: Optional[List[Optional[Dict[str, Any]]]] = None,
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    clips: List[CompositeVideoClip] = []
    transition_specs: List[Optional[Dict[str, Any]]] = []
    motions = motions or [None] * len(images)

    for img, audio, motion in zip(images, audio_files, motions):
        with AudioFileClip(audio) as aclip:
            duration = aclip.duration
            ic = ImageClip(img)
            scale = min(width / ic.w, height / ic.h)
            bg = ColorClip((width, height), color=_hex_to_rgb(bg_color)).set_duration(
                duration
            )

            mtype = None
            amount = 0.0
            if isinstance(motion, dict):
                mtype = motion.get("type")
                try:
                    amount = float(motion.get("amount", 0.05))
                except Exception:  # pragma: no cover - defensive
                    amount = 0.05
                amount = max(0.0, min(0.25, amount))

            if mtype in ("zoom-in", "zoom-out") and amount > 0:
                start_s, end_s = _compute_zoom_scales(scale, mtype, amount)

                def scaler(t):  # pragma: no cover - MoviePy callback
                    if duration <= 0:
                        return scale
                    p = max(0.0, min(1.0, t / duration))
                    return start_s + (end_s - start_s) * p

                moving = ic.resize(lambda t: scaler(t)).set_duration(duration)
                comp = CompositeVideoClip([bg, moving.set_position("center")])
            elif mtype in (
                "pan-left",
                "pan-right",
                "pan-up",
                "pan-down",
            ) and amount > 0:
                moving = ic.resize(scale).set_duration(duration)
                shift = int(amount * 0.25 * min(width, height))

                def pos_func(t):  # pragma: no cover - MoviePy callback
                    if duration <= 0:
                        return (width / 2 - moving.w / 2, height / 2 - moving.h / 2)
                    p = max(0.0, min(1.0, t / duration))
                    dx0 = dy0 = 0
                    dx1 = dy1 = 0
                    if mtype == "pan-left":
                        dx0, dx1 = +shift, -shift
                    elif mtype == "pan-right":
                        dx0, dx1 = -shift, +shift
                    elif mtype == "pan-up":
                        dy0, dy1 = +shift, -shift
                    elif mtype == "pan-down":
                        dy0, dy1 = -shift, +shift
                    dx = dx0 + (dx1 - dx0) * p
                    dy = dy0 + (dy1 - dy0) * p
                    cx = width / 2 + dx
                    cy = height / 2 + dy
                    return (cx - moving.w / 2, cy - moving.h / 2)

                comp = CompositeVideoClip(
                    [bg, moving.set_position(lambda t: pos_func(t))]
                )
            else:
                still = ic.resize(scale).set_duration(duration)
                comp = CompositeVideoClip([bg, still.set_position("center")])

            vclip = comp.set_audio(aclip)
            clips.append(vclip)
            transition_specs.append(_parse_transition_spec(motion))

    final = _compose_with_transitions(clips, transition_specs)
    final = final.set_fps(fps)

    final.write_videofile(
        output_path,
        codec="libx264",
        preset="veryfast",
        audio_codec="aac",
        audio_bitrate="128k",
        fps=fps,
        threads=0,
        ffmpeg_params=["-crf", "23", "-movflags", "+faststart"],
    )
    final.close()
    for clip in clips:
        clip.close()


def _escape_ffmpeg_subtitles_path(path: str) -> str:
    normalized = os.path.abspath(path).replace("\\", "/")
    normalized = normalized.replace(":", "\\:").replace("'", r"\'")
    return normalized


async def burn_subtitles(input_video: str, srt_path: str, output_video: str) -> None:
    escaped_path = _escape_ffmpeg_subtitles_path(srt_path)
    vf = f"subtitles=filename='{escaped_path}'"
    if not srt_path.lower().endswith(".ass"):
        vf += ":force_style='Fontsize=24,PrimaryColour=&HFFFFFF&'"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_video,
        "-vf",
        vf,
        "-c:a",
        "copy",
        output_video,
    ]
    subprocess.run(cmd, check=True)


async def append_video(main_video: str, tail_video: str, output_video: str) -> None:
    def ensure_mp4_same_size(src: str, ref: str, out: str) -> None:
        probe = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            ref,
        ]
        proc = subprocess.run(
            probe, capture_output=True, text=True, check=True
        )
        width, height = (int(x) for x in proc.stdout.strip().split(","))
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src,
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                out,
            ],
            check=True,
        )

    work_dir = Path(output_video).parent
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_main = work_dir / "_main.mp4"
    temp_tail = work_dir / "_tail.mp4"
    ensure_mp4_same_size(main_video, main_video, str(temp_main))
    ensure_mp4_same_size(tail_video, main_video, str(temp_tail))

    concat_file = work_dir / "concat.txt"
    with concat_file.open("w", encoding="utf-8") as f:
        main_safe = str(temp_main).replace("\\", "/")
        tail_safe = str(temp_tail).replace("\\", "/")
        f.write(f"file '{main_safe}'\n")
        f.write(f"file '{tail_safe}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            output_video,
        ],
        check=True,
    )

    for path in (temp_main, temp_tail, concat_file):
        with contextlib.suppress(Exception):
            Path(path).unlink()
