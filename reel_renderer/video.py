"""High-level MoviePy helpers used by the render pipeline."""

from __future__ import annotations

import contextlib
import math
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


_ENCODER_CACHE: Dict[Tuple[str, str], bool] = {}


def _resolve_ffmpeg_binary() -> str:
    override = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if override:
        return override.strip().strip('"')

    try:  # pragma: no cover - defensive import
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _ffmpeg_has_encoder(name: str) -> bool:
    """Return True if the local ffmpeg build exposes the given encoder."""

    binary = _resolve_ffmpeg_binary()
    cache_key = (binary, name)
    if cache_key in _ENCODER_CACHE:
        return _ENCODER_CACHE[cache_key]

    try:
        result = subprocess.run(
            [binary, "-hide_banner", "-loglevel", "error", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
        )
        available = name in result.stdout
    except Exception:
        available = False

    _ENCODER_CACHE[cache_key] = available

    if name == "h264_nvenc" and not available:
        print(f"Encoder h264_nvenc not available in ffmpeg binary at {binary}")

    return available


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


def _extract_transform(
    transform: Optional[Dict[str, Any]]
) -> Tuple[float, float, float]:
    if not isinstance(transform, dict):
        return 1.0, 0.0, 0.0

    scale_raw = transform.get("scale")
    scale_val = 1.0
    if isinstance(scale_raw, (int, float)) and math.isfinite(scale_raw) and scale_raw > 0:
        scale_val = float(scale_raw)
    else:
        try:
            candidate = float(scale_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            candidate = 1.0
        if math.isfinite(candidate) and candidate > 0:
            scale_val = candidate
    scale_val = max(0.5, min(scale_val, 6.0))

    def _resolve_offset(primary: str, secondary: str) -> float:
        raw = transform.get(primary)
        if raw is None:
            raw = transform.get(secondary)
        if isinstance(raw, (int, float)) and math.isfinite(raw):
            return float(raw)
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = 0.0
        if not math.isfinite(value):
            return 0.0
        return value

    offset_x = _resolve_offset("offset_x", "offsetX")
    offset_y = _resolve_offset("offset_y", "offsetY")

    return scale_val, offset_x, offset_y


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


def _render_via_prerender(
    clip,
    output_path: str,
    fps: int,
    codec: str,
    preset: str,
    bitrate: Optional[str] = None
) -> None:
    """
    Pre-render all frames to PNG files, then encode with FFmpeg NVENC in one pass.
    This separates frame generation (CPU) from encoding (GPU) for better performance.
    """
    import tempfile
    import shutil
    from PIL import Image
    import numpy as np
    
    # Create temp directory for frames
    frames_dir = tempfile.mkdtemp(prefix="render_frames_")
    
    try:
        # Extract audio to temp file
        audio_path = None
        if clip.audio is not None:
            audio_path = os.path.join(frames_dir, "audio.aac")
            print(f"📼 Extracting audio to {audio_path}")
            try:
                clip.audio.write_audiofile(
                    audio_path, 
                    codec="aac", 
                    bitrate="128k", 
                    fps=44100,  # Audio sample rate
                    verbose=False, 
                    logger=None
                )
            except Exception as e:
                print(f"⚠️  Audio extraction failed: {e}, continuing without audio")
                audio_path = None
        
        # Pre-render all frames to PNG (parallel)
        import time
        total_frames = int(clip.duration * fps)
        print(f"🖼️  Pre-rendering {total_frames} frames to PNG (parallel)...")
        
        start_time = time.time()
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def render_frame(frame_idx):
            """Render single frame to PNG"""
            t = frame_idx / fps
            frame = clip.get_frame(t)
            frame_path = os.path.join(frames_dir, f"frame_{frame_idx:06d}.png")
            Image.fromarray(frame).save(frame_path, compress_level=1)
            return frame_idx
        
        # Parallel rendering with 8 workers
        completed = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(render_frame, i): i for i in range(total_frames)}
            for future in as_completed(futures):
                completed += 1
                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    fps_rate = completed / elapsed if elapsed > 0 else 0
                    print(f"   Rendered {completed}/{total_frames} frames ({fps_rate:.1f} fps, {elapsed:.1f}s elapsed)")
        
        elapsed_total = time.time() - start_time
        fps_rate_total = total_frames / elapsed_total if elapsed_total > 0 else 0
        print(f"✅ All {total_frames} frames pre-rendered in {elapsed_total:.1f}s ({fps_rate_total:.1f} fps)")
        
        # Encode with FFmpeg NVENC
        print(f"🎬 Encoding video with {codec}...")
        encode_start = time.time()
        
        ffmpeg_cmd = [
            _resolve_ffmpeg_binary(),
            "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.png"),
        ]
        
        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend(["-i", audio_path])
        
        ffmpeg_cmd.extend([
            "-c:v", codec,
        ])
        
        if codec == "h264_nvenc":
            ffmpeg_cmd.extend([
                "-preset", preset,
                "-b:v", bitrate or "8M",
            ])
        else:
            ffmpeg_cmd.extend([
                "-preset", preset,
                "-crf", "23",
            ])
        
        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend(["-c:a", "copy"])
        
        ffmpeg_cmd.extend([
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            output_path
        ])
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg encoding failed: {result.stderr}")
        
        encode_elapsed = time.time() - encode_start
        print(f"✅ Video encoded successfully in {encode_elapsed:.1f}s")
        
    finally:
        # Cleanup temp directory
        shutil.rmtree(frames_dir, ignore_errors=True)


async def assemble_video_with_audio(
    images: List[str],
    audio_files: List[str],
    width: int,
    height: int,
    fps: int,
    bg_color: str,
    output_path: str,
    motions: Optional[List[Optional[Dict[str, Any]]]] = None,
    transforms: Optional[List[Optional[Dict[str, Any]]]] = None,
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    clips: List[CompositeVideoClip] = []
    transition_specs: List[Optional[Dict[str, Any]]] = []
    motions = motions or [None] * len(images)

    audio_clips: List[AudioFileClip] = []

    for idx, (img, audio) in enumerate(zip(images, audio_files)):
        motion = motions[idx] if idx < len(motions) else None
        transform_dict = (
            transforms[idx]
            if transforms and idx < len(transforms)
            else None
        )
        transform_scale, offset_x, offset_y = _extract_transform(transform_dict)

        aclip = AudioFileClip(audio)
        audio_clips.append(aclip)

        duration = aclip.duration
        ic = ImageClip(img)
        base_scale = min(width / ic.w, height / ic.h)
        scale = base_scale * transform_scale
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

            def pos_func(t):  # pragma: no cover - MoviePy callback
                scale_t = scaler(t)
                w_t = ic.w * scale_t
                h_t = ic.h * scale_t
                cx = width / 2 + offset_x
                cy = height / 2 + offset_y
                return (cx - w_t / 2, cy - h_t / 2)

            comp = CompositeVideoClip([bg, moving.set_position(pos_func)])
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
                    cx_default = width / 2 + offset_x
                    cy_default = height / 2 + offset_y
                    return (cx_default - moving.w / 2, cy_default - moving.h / 2)
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
                cx = width / 2 + offset_x + dx
                cy = height / 2 + offset_y + dy
                return (cx - moving.w / 2, cy - moving.h / 2)

            comp = CompositeVideoClip([bg, moving.set_position(lambda t: pos_func(t))])
        else:
            still = ic.resize(scale).set_duration(duration)
            cx = width / 2 + offset_x
            cy = height / 2 + offset_y
            comp = CompositeVideoClip(
                [bg, still.set_position((cx - still.w / 2, cy - still.h / 2))]
            )

        vclip = comp.set_audio(aclip)
        clips.append(vclip)
        transition_specs.append(_parse_transition_spec(motion))

    final = _compose_with_transitions(clips, transition_specs)
    final = final.set_fps(fps)

    nvenc_requested = os.environ.get("RENDER_USE_NVENC") == "1"
    use_nvenc = nvenc_requested and _ffmpeg_has_encoder("h264_nvenc")
    if use_nvenc:
        preset = os.environ.get("RENDER_NVENC_PRESET", "p6")
        bitrate = os.environ.get("RENDER_NVENC_BITRATE", "8M")
        codec = "h264_nvenc"
        ffmpeg_params = ["-preset", preset, "-b:v", bitrate, "-movflags", "+faststart"]
        # threads=4 is optimal balance: enough parallelism without overhead
        threads = 4
    else:
        if nvenc_requested:
            print("NVENC requested but encoder 'h264_nvenc' not available; falling back to libx264")
        codec = "libx264"
        preset = "veryfast"
        ffmpeg_params = ["-crf", "23", "-movflags", "+faststart"]
        threads = 4

    # Choose rendering mode: live (default) or prerender (faster with NVENC)
    render_mode = os.environ.get("RENDER_MODE", "live")
    
    if render_mode == "prerender":
        print(f"🎬 Pre-rendering frames to PNG, then encoding with {codec}")
        _render_via_prerender(final, output_path, fps, codec, preset, bitrate if use_nvenc else None)
    else:
        def _encode(encoder: str, params: list[str], preset_value: str) -> None:
            print(f"Rendering video with codec: {encoder}, preset: {preset_value}")
            final.write_videofile(
                output_path,
                codec=encoder,
                preset=preset_value,
                audio_codec="aac",
                audio_bitrate="128k",
                fps=fps,
                threads=threads,
                ffmpeg_params=params,
            )

        try:
            _encode(codec, ffmpeg_params, preset)
        except (BrokenPipeError, IOError, OSError, RuntimeError) as e:
            # Handle pipe errors which can occur when FFmpeg crashes or is interrupted
            error_msg = f"FFmpeg pipe error during video writing: {e}"
            print(error_msg)
            if use_nvenc:
                print("⚠️ NVENC failed; falling back to libx264 software encoding")
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                fallback_codec = "libx264"
                fallback_preset = "veryfast"
                fallback_params = ["-crf", "23", "-movflags", "+faststart"]
                try:
                    _encode(fallback_codec, fallback_params, fallback_preset)
                except Exception as fallback_err:  # pragma: no cover - defensive
                    print(f"❌ Fallback encoding failed: {fallback_err}")
                    raise RuntimeError(error_msg) from fallback_err
            else:
                if os.path.exists(output_path):
                    size = os.path.getsize(output_path)
                    print(f"Partial output exists: {size} bytes")
                raise RuntimeError(error_msg) from e
    
    final.close()
    for clip in clips:
        clip.close()
    for aclip in audio_clips:
        with contextlib.suppress(Exception):
            aclip.close()


def _escape_ffmpeg_subtitles_path(path: str) -> str:
    normalized = os.path.abspath(path).replace("\\", "/")
    normalized = normalized.replace(":", "\\:").replace("'", r"\'")
    return normalized


async def burn_subtitles(input_video: str, srt_path: str, output_video: str) -> None:
    escaped_path = _escape_ffmpeg_subtitles_path(srt_path)
    vf = f"subtitles=filename='{escaped_path}'"
    if not srt_path.lower().endswith(".ass"):
        vf += ":force_style='Fontsize=24,PrimaryColour=&HFFFFFF&'"
    
    # Use NVENC if available for GPU acceleration
    use_nvenc = os.environ.get("RENDER_USE_NVENC", "0") == "1"
    codec = "h264_nvenc" if use_nvenc and _ffmpeg_has_encoder("h264_nvenc") else "libx264"
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_video,
        "-vf",
        vf,
        "-c:v",
        codec,
    ]
    
    # Add NVENC-specific settings if using GPU encoder
    if codec == "h264_nvenc":
        cmd.extend([
            "-preset", "p6",  # p6 = higher quality preset
            "-b:v", "8M",
        ])
    
    cmd.extend([
        "-c:a",
        "copy",
        output_video,
    ])
    
    print(f"🔥 Burning subtitles with codec: {codec}")
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
