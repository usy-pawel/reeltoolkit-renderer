"""Modal.com serverless handler for ReelToolkit Renderer.

GPU-accelerated ffmpeg rendering with NVIDIA NVENC on Modal.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import modal  # type: ignore[import-not-found]

APP_NAME = "reeltoolkit-renderer"
BASE_DIR = Path(__file__).resolve().parent

# Create Modal app
app = modal.App(APP_NAME)
_render_secret = modal.Secret.from_name("reel-secrets")

# Use NVIDIA CUDA base image with GPU support + build FFmpeg with NVENC from source
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.2.0-devel-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install(
        "git",
        "build-essential",
        "yasm",
        "nasm",
        "pkg-config",
        "libx264-dev",
        "libx265-dev",
        "libnuma-dev",
        "libvpx-dev",
        "libmp3lame-dev",
        "libopus-dev",
        "libass-dev",
        "libfreetype6-dev",
        "libfontconfig1-dev",
        "libfribidi-dev",
        "wget",
    )
    .run_commands(
        # Install NVIDIA codec headers (required for NVENC/NVDEC)
        "git clone --depth 1 --branch n12.1.14.0 https://git.videolan.org/git/ffmpeg/nv-codec-headers.git /tmp/nv-codec-headers",
        "cd /tmp/nv-codec-headers && make install PREFIX=/usr/local",
        # Download FFmpeg source
        "git clone --depth 1 --branch n6.1.1 https://git.ffmpeg.org/ffmpeg.git /tmp/ffmpeg",
        # Configure FFmpeg with NVENC
        "cd /tmp/ffmpeg && ./configure "
        "--prefix=/usr/local "
        "--enable-gpl "
        "--enable-nonfree "
        "--enable-libx264 "
        "--enable-libx265 "
        "--enable-libvpx "
        "--enable-libmp3lame "
        "--enable-libopus "
        "--enable-libass "
        "--enable-libfreetype "
        "--enable-libfontconfig "
        "--enable-libfribidi "
        "--enable-cuda-nvcc "
        "--enable-cuvid "
        "--enable-nvenc "
        "--enable-nvdec "
        "--enable-libnpp "
        "--extra-cflags='-I/usr/local/cuda/include' "
        "--extra-ldflags='-L/usr/local/cuda/lib64'",
        # Build FFmpeg
        "cd /tmp/ffmpeg && make -j$(nproc)",
        # Install FFmpeg
        "cd /tmp/ffmpeg && make install",
        # Cleanup build files to reduce image size
        "rm -rf /tmp/ffmpeg /tmp/nv-codec-headers",
        # Update library cache and verify
        "ldconfig",
        "ffmpeg -version | head -n 1",
        "ffmpeg -hide_banner -encoders 2>/dev/null | grep nvenc || echo 'NVENC encoder will be available at runtime with GPU'",
    )
    .pip_install(
        "fastapi[standard]",
        "pydantic==2.8.2",
        "typing_extensions>=4.9.0",
        "numpy",
        "Pillow",
        "imageio==2.34.0",
        "imageio-ffmpeg==0.4.9",
        "moviepy==1.0.3",
    )
    .run_commands(
        "bash -lc 'set -e; "
    "IMAGEIO_FFMPEG_DIR=$(python -c \"import imageio_ffmpeg, os; print(os.path.dirname(imageio_ffmpeg.__file__))\"); "
        "mkdir -p $IMAGEIO_FFMPEG_DIR/binaries; "
        "rm -f $IMAGEIO_FFMPEG_DIR/binaries/ffmpeg-linux*; "
        "ln -sf /usr/local/bin/ffmpeg $IMAGEIO_FFMPEG_DIR/binaries/ffmpeg-linux64-v4.2.2; "
        "ln -sf /usr/local/bin/ffprobe $IMAGEIO_FFMPEG_DIR/binaries/ffprobe-linux64-v4.2.2'"
    )
    .add_local_dir(str(BASE_DIR / "reel_renderer"), remote_path="/root/reel_renderer")
    .add_local_file(str(Path(__file__).resolve()), remote_path="/root/modal_app.py")
)

_GPU_PRESETS = {
    "L4": "L4",
    "L40S": "L40S",
}

_DEFAULT_GPU_RATES = {
    "L4": 0.35,
    "L40S": 1.95,
}

# Allow additional alias spellings to resolve to supported presets.
_GPU_ALIAS_SYNONYMS = {
    "L40": "L40S",
    "L4S": "L40S",
}


def _resolve_timeout_seconds(env_key: str, default_value: int) -> int:
    raw_value = os.getenv(env_key)
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value)
        if parsed <= 0:
            raise ValueError
        print(f"⚙️ Modal timeout override: {env_key}={parsed}s")
        return parsed
    except ValueError:
        print(
            f"⚠️ Invalid timeout override in {env_key}={raw_value!r}; using default {default_value}s"
        )
        return default_value


GPU_RENDER_TIMEOUT_SECONDS = _resolve_timeout_seconds(
    "MODAL_GPU_TIMEOUT_SECONDS",
    1800,
)

ENTRYPOINT_TIMEOUT_SECONDS = _resolve_timeout_seconds(
    "MODAL_RENDER_TIMEOUT_SECONDS",
    GPU_RENDER_TIMEOUT_SECONDS + 120,
)

if ENTRYPOINT_TIMEOUT_SECONDS <= GPU_RENDER_TIMEOUT_SECONDS:
    adjusted_timeout = GPU_RENDER_TIMEOUT_SECONDS + 60
    print(
        "ℹ️ Modal entrypoint timeout ({entry}s) is not larger than GPU timeout ({gpu}s); adjusting to {adjusted}s".format(
            entry=ENTRYPOINT_TIMEOUT_SECONDS,
            gpu=GPU_RENDER_TIMEOUT_SECONDS,
            adjusted=adjusted_timeout,
        )
    )
    ENTRYPOINT_TIMEOUT_SECONDS = adjusted_timeout

print(
    "⚙️ Modal GPU timeout configured: {gpu}s | entrypoint timeout: {entry}s".format(
        gpu=GPU_RENDER_TIMEOUT_SECONDS,
        entry=ENTRYPOINT_TIMEOUT_SECONDS,
    )
)


def _resolve_gpu_config(raw_value: str | None) -> str:
    if raw_value is not None:
        stripped = raw_value.strip()
        if stripped:
            alias = stripped.upper()
            if alias in _GPU_PRESETS:
                resolved = _GPU_PRESETS[alias]
                print(f"⚙️ Modal GPU preset '{alias}' resolved to '{resolved}'")
                return resolved
            print(f"⚙️ Modal GPU override '{stripped}' not in presets; using raw value.")
            return stripped
    default_gpu = _GPU_PRESETS["L4"]
    print(f"⚙️ Modal GPU not specified; defaulting to '{default_gpu}'")
    return default_gpu


GPU_CONFIG = _resolve_gpu_config(os.environ.get("MODAL_RENDER_GPU"))
print(f"⚙️ Modal GPU configured at deploy time: {GPU_CONFIG}")


def _log_gpu_info(context: str) -> None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print(f"🎮 GPU detected during {context}: {result.stdout.strip()}")
        else:
            print(f"⚠️ nvidia-smi failed during {context}: {result.stderr.strip()}")
    except FileNotFoundError:
        print(f"⚠️ nvidia-smi not available during {context}")
    except Exception as exc:  # pragma: no cover - telemetry only
        print(f"⚠️ Could not query GPU during {context}: {exc}")


def _resolve_gpu_rate(gpu_name: str) -> tuple[float | None, str]:
    env_key_specific = f"MODAL_GPU_RATE_USD_PER_HOUR_{gpu_name.replace('-', '_')}"
    raw_specific = os.getenv(env_key_specific)
    if raw_specific:
        try:
            return float(raw_specific), env_key_specific
        except ValueError:
            print(f"⚠️ Invalid float in {env_key_specific}={raw_specific!r}; ignoring")

    overrides = os.getenv("MODAL_GPU_RATE_OVERRIDES")
    if overrides:
        try:
            data = json.loads(overrides)
            if isinstance(data, dict) and gpu_name in data:
                return float(data[gpu_name]), "MODAL_GPU_RATE_OVERRIDES"
        except Exception as exc:  # pragma: no cover
            print(f"⚠️ Failed to parse MODAL_GPU_RATE_OVERRIDES: {exc}")

    raw_global = os.getenv("MODAL_GPU_RATE_USD_PER_HOUR")
    if raw_global:
        try:
            return float(raw_global), "MODAL_GPU_RATE_USD_PER_HOUR"
        except ValueError:
            print(
                f"⚠️ Invalid float in MODAL_GPU_RATE_USD_PER_HOUR={raw_global!r}; ignoring"
            )

    if gpu_name in _DEFAULT_GPU_RATES:
        return _DEFAULT_GPU_RATES[gpu_name], "default"

    return None, "unset"


def _estimate_render_cost(
    gpu_name: str,
    duration_seconds: float,
    *,
    dimensions: tuple[int, int] | None = None,
) -> dict[str, object]:
    duration_seconds = max(float(duration_seconds), 0.0)
    rate, source = _resolve_gpu_rate(gpu_name)
    summary: dict[str, object] = {
        "gpu": gpu_name,
        "duration_seconds": duration_seconds,
        "gpu_rate_usd_per_hour": rate,
        "gpu_rate_source": source,
        "cost_usd": None,
    }
    if dimensions:
        width, height = dimensions
        summary["render_dimensions"] = f"{int(width)}x{int(height)}"
    if rate is None:
        print(
            f"⚠️ No GPU rate configured for {gpu_name}; cost estimate unavailable (source={source})"
        )
        return summary
    cost = rate * (duration_seconds / 3600.0)
    summary["cost_usd"] = cost
    print(
        "💵 Estimated GPU cost: ${cost:.4f} (gpu={gpu}, duration={dur:.1f}s, rate=${rate:.4f}/hr via {source})".format(
            cost=cost,
            gpu=gpu_name,
            dur=duration_seconds,
            rate=rate,
            source=source,
        )
    )
    return summary


def _override_dimensions(spec, target_width: int = 360) -> None:
    try:
        current_width = float(spec.dimensions.width)
        current_height = float(spec.dimensions.height)
    except Exception:
        return
    if current_width <= 0 or target_width <= 0:
        return
    if int(current_width) == int(target_width):
        return
    aspect_ratio = current_height / current_width if current_width else 16 / 9
    new_width = int(target_width)
    if new_width % 2 != 0:
        new_width += 1
    new_height = int(round(new_width * aspect_ratio))
    if new_height % 2 != 0:
        new_height += 1
    print(
        f"📏 Overriding render dimensions: {int(current_width)}x{int(current_height)} -> {new_width}x{new_height}"
    )
    spec.dimensions.width = new_width
    spec.dimensions.height = new_height


@app.function(
    image=image,
    timeout=600,  # 10 minutes max
    memory=2048,
    secrets=[_render_secret],
)
def test_ffmpeg():
    """Generate a short test video using FFmpeg."""
    _log_gpu_info("test_ffmpeg")
    print("🎬 Generating test video with ffmpeg...")
    tmp_dir = tempfile.mkdtemp(prefix="modal_ffmpeg_")
    out_path = Path(tmp_dir) / "test.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=720x1280:d=1:r=25",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ FFmpeg success: {result.stderr[-200:]}")
        video_bytes = out_path.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode("utf-8")
        return {
            "success": True,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64,
            "message": "Test video generated successfully",
        }
    except subprocess.CalledProcessError as exc:
        print(f"❌ FFmpeg failed: {exc.stderr}")
        return {"success": False, "error": exc.stderr}
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.function(
    image=image,
    gpu=GPU_CONFIG,
    timeout=300,
    secrets=[_render_secret],
)
def encode_frames_railway(
    frames_zip_b64: str,
    audio_b64: str = "",
    subtitles_ass_b64: str = "",
    fps: int = 30,
    job_id: str = "unknown",
) -> dict[str, object]:
    import glob
    import shutil
    import tempfile
    import zipfile

    job_start = time.perf_counter()
    print(f"📦 Railway mode: Received pre-rendered frames for job {job_id}")
    _log_gpu_info("encode_frames_railway")
    os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/local/bin/ffmpeg"
    work_dir = tempfile.mkdtemp(prefix=f"railway_{job_id}_")
    try:
        frames_dir = os.path.join(work_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        zip_bytes = base64.b64decode(frames_zip_b64)
        zip_path = os.path.join(work_dir, "frames.zip")
        with open(zip_path, "wb") as dst:
            dst.write(zip_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(frames_dir)
        frame_files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.png")))
        print(f"📊 Extracted {len(frame_files)} frames")
        audio_path = None
        if audio_b64:
            audio_path = os.path.join(work_dir, "audio.aac")
            with open(audio_path, "wb") as dst:
                dst.write(base64.b64decode(audio_b64))
        base_video = os.path.join(work_dir, "base.mp4")
        print(f"🎬 Encoding {len(frame_files)} frames with h264_nvenc @ {fps}fps...")
        encode_start = time.time()
        ffmpeg_cmd = [
            "/usr/local/bin/ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            os.path.join(frames_dir, "frame_%06d.png"),
        ]
        if audio_path:
            ffmpeg_cmd.extend(["-i", audio_path, "-c:a", "copy"])
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p6",
                "-b:v",
                "8M",
                "-movflags",
                "+faststart",
                "-pix_fmt",
                "yuv420p",
                base_video,
            ]
        )
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"NVENC encoding failed: {result.stderr}")
        encode_elapsed = time.time() - encode_start
        print(f"✅ Base video encoded in {encode_elapsed:.1f}s")
        final_video = base_video
        if subtitles_ass_b64:
            print("🔥 Burning subtitles with h264_nvenc...")
            subtitles_path = os.path.join(work_dir, "subtitles.ass")
            with open(subtitles_path, "wb") as dst:
                dst.write(base64.b64decode(subtitles_ass_b64))
            subbed_video = os.path.join(work_dir, "subbed.mp4")
            escaped_path = (
                subtitles_path.replace("\\", "/").replace(":", "\\:").replace("'", r"\'")
            )
            sub_cmd = [
                "/usr/local/bin/ffmpeg",
                "-y",
                "-i",
                base_video,
                "-vf",
                f"subtitles=filename='{escaped_path}'",
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p6",
                "-b:v",
                "8M",
                "-c:a",
                "copy",
                subbed_video,
            ]
            result = subprocess.run(sub_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                final_video = subbed_video
                print("✅ Subtitles burned")
        with open(final_video, "rb") as src:
            video_bytes = src.read()
        print(f"✅ Railway mode complete: {len(video_bytes)} bytes")
        duration_seconds = time.perf_counter() - job_start
        cost_summary = _estimate_render_cost(GPU_CONFIG, duration_seconds)
        result_dict: dict[str, object] = {
            "job_id": job_id,
            "video_b64": base64.b64encode(video_bytes).decode("utf-8"),
            "size_bytes": len(video_bytes),
            "success": True,
        }
        result_dict.update(cost_summary)
        return result_dict
    except Exception as exc:
        import traceback

        error_msg = f"{exc}\n{traceback.format_exc()}"
        print(f"❌ Railway mode failed: {error_msg}")
        duration_seconds = time.perf_counter() - job_start
        cost_summary = _estimate_render_cost(GPU_CONFIG, duration_seconds)
        result_dict = {
            "job_id": job_id,
            "success": False,
            "error": error_msg,
        }
        result_dict.update(cost_summary)
        return result_dict
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _extract_requested_gpu(spec_dict: dict | None) -> str | None:
    if not isinstance(spec_dict, dict):
        return None
    render_section = spec_dict.get("render")
    if isinstance(render_section, dict):
        gpu_value = render_section.get("gpu_preset")
        if isinstance(gpu_value, str):
            return gpu_value
    gpu_fallback = spec_dict.get("gpu_preset")
    if isinstance(gpu_fallback, str):
        return gpu_fallback
    return None


def _render_reel_impl(spec_dict: dict, bundle_b64: str, *, gpu_name: str) -> dict[str, object]:
    import asyncio
    import shutil
    import zipfile

    from reel_renderer.pipeline import render_reel as do_render_async
    from reel_renderer.types import RenderJobSpec

    print(
        f"📦 Received render job: {spec_dict.get('job_id', 'unknown')} on GPU {gpu_name}"
    )
    os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/local/bin/ffmpeg"
    os.environ["RENDER_USE_NVENC"] = "1"
    os.environ["RENDER_MODE"] = "prerender"
    _log_gpu_info(f"render_reel[{gpu_name}]")
    job_start = time.perf_counter()
    tmp_dir = Path(tempfile.mkdtemp(prefix="modal_render_"))
    bundle_zip = tmp_dir / "bundle.zip"
    bundle_dir = tmp_dir / "bundle"
    output_video = tmp_dir / "output.mp4"
    try:
        bundle_zip.write_bytes(base64.b64decode(bundle_b64))
        print(f"📁 Bundle size: {bundle_zip.stat().st_size} bytes")
        bundle_dir.mkdir()
        with zipfile.ZipFile(bundle_zip) as zf:
            zf.extractall(bundle_dir)
        print(f"📂 Extracted to: {bundle_dir}")
        spec = RenderJobSpec.model_validate(spec_dict)
        requested_gpu = spec.render.gpu_preset
        if requested_gpu:
            print(
                f"🎯 Job requested GPU preset '{requested_gpu}'; executing on '{gpu_name}'"
            )
        if (spec.render.quality or "final").lower() == "draft":
            _override_dimensions(spec, target_width=360)
        else:
            print(
                f"📐 Preserving requested resolution for quality '{spec.render.quality or 'final'}'"
            )
        print(
            f"📐 Using render dimensions: {spec.dimensions.width}x{spec.dimensions.height}"
        )
        print(
            f"🎬 Starting GPU render: {spec.dimensions.width}x{spec.dimensions.height} @ {spec.dimensions.fps}fps"
        )
        print(f"🔧 FFmpeg path: {os.environ.get('IMAGEIO_FFMPEG_EXE')}")
        print(f"🎥 NVENC enabled: {os.environ.get('RENDER_USE_NVENC')}")
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                check=True,
            )
            if "h264_nvenc" in result.stdout:
                print("✅ h264_nvenc encoder is available")
            else:
                print("❌ WARNING: h264_nvenc encoder NOT FOUND!")
                print("Available H264 encoders:")
                for line in result.stdout.split("\n"):
                    if "h264" in line.lower():
                        print(f"  {line}")
        except Exception as ffmpeg_err:
            print(f"⚠️ FFmpeg encoder check failed: {ffmpeg_err}")
        final_dimensions = (spec.dimensions.width, spec.dimensions.height)
        asyncio.run(
            do_render_async(
                spec=spec,
                bundle_path=bundle_dir,
                output_path=output_video,
            )
        )
        video_bytes = output_video.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode("utf-8")
        print(f"✅ Render complete: {len(video_bytes)} bytes")
        duration_seconds = time.perf_counter() - job_start
        cost_summary = _estimate_render_cost(
            gpu_name,
            duration_seconds,
            dimensions=final_dimensions,
        )
        result_dict: dict[str, object] = {
            "success": True,
            "job_id": spec.job_id,
            "size_bytes": len(video_bytes),
            "video_b64": video_b64,
            "inline": True,
        }
        result_dict.update(cost_summary)
        return result_dict
    except Exception as exc:
        import traceback

        print(f"❌ Render failed: {exc}")
        duration_seconds = time.perf_counter() - job_start
        cost_summary = _estimate_render_cost(
            gpu_name,
            duration_seconds,
            dimensions=(spec.dimensions.width, spec.dimensions.height)
            if "spec" in locals()
            else None,
        )
        result_dict = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        result_dict.update(cost_summary)
        return result_dict
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


_GPU_ALIAS_TO_RESOLVED: dict[str, str] = {alias.upper(): value for alias, value in _GPU_PRESETS.items()}
_GPU_FUNCTIONS: dict[str, modal.Function] = {}
_GPU_FUNCTION_NAMES: dict[str, str] = {}
_GPU_KEY_TO_ALIAS: dict[str, str] = {}


def _alias_for_resolved(resolved_name: str) -> str:
    for alias, resolved in _GPU_PRESETS.items():
        if resolved.upper() == resolved_name.upper():
            return alias.upper()
    return resolved_name.upper()


def _register_render_function(alias: str, resolved_name: str) -> None:
    normalized_alias = alias.upper()
    normalized_resolved = resolved_name.upper()
    modal_name = f"render_reel_{normalized_alias.lower().replace('-', '_')}"
    def _factory(gpu_name: str):
        def _render(spec_dict: dict, bundle_b64: str) -> dict[str, object]:
            return _render_reel_impl(spec_dict, bundle_b64, gpu_name=gpu_name)

        return _render

    render_impl = _factory(resolved_name)

    try:
        decorated = app.function(
            name=modal_name,
            image=image,
            timeout=GPU_RENDER_TIMEOUT_SECONDS,
            memory=8192,
            gpu=resolved_name,
            secrets=[_render_secret],
            serialized=True,
        )(render_impl)
    except Exception as exc:
        print(f"⚠️ Skipping GPU preset '{alias}' ({resolved_name}): {exc}")
        return

    _GPU_FUNCTIONS[normalized_alias] = decorated
    _GPU_FUNCTIONS[normalized_resolved] = decorated
    _GPU_FUNCTION_NAMES[normalized_alias] = modal_name
    _GPU_FUNCTION_NAMES[normalized_resolved] = modal_name
    _GPU_KEY_TO_ALIAS[normalized_alias] = normalized_alias
    _GPU_KEY_TO_ALIAS[normalized_resolved] = normalized_alias
    _GPU_ALIAS_TO_RESOLVED[normalized_alias] = resolved_name


for alias, resolved in _GPU_PRESETS.items():
    _register_render_function(alias, resolved)


_DEFAULT_GPU_ALIAS = _alias_for_resolved(GPU_CONFIG)
if _DEFAULT_GPU_ALIAS not in _GPU_FUNCTIONS:
    _register_render_function(_DEFAULT_GPU_ALIAS, GPU_CONFIG)

render_reel_default: modal.Function = _GPU_FUNCTIONS[_DEFAULT_GPU_ALIAS]
GPU_RENDER_FUNCTIONS = dict(_GPU_FUNCTIONS)


def _resolve_gpu_function(requested_gpu: str | None) -> tuple[str, modal.Function]:
    if requested_gpu:
        key = requested_gpu.strip().upper()
        canonical_key = _GPU_ALIAS_SYNONYMS.get(key, key)
        if canonical_key != key:
            print(
                f"ℹ️ GPU alias '{requested_gpu}' normalized to preset '{canonical_key}'"
            )
        alias = _GPU_KEY_TO_ALIAS.get(canonical_key)
        if alias and alias in _GPU_FUNCTIONS:
            return alias, _GPU_FUNCTIONS[alias]
        print(
            f"⚠️ Requested GPU '{requested_gpu}' not available; falling back to '{_DEFAULT_GPU_ALIAS}'"
        )
    return _DEFAULT_GPU_ALIAS, _GPU_FUNCTIONS[_DEFAULT_GPU_ALIAS]


def render_reel_for_request(spec_dict: dict, bundle_b64: str) -> dict[str, object]:
    requested_gpu = _extract_requested_gpu(spec_dict)
    alias, function = _resolve_gpu_function(requested_gpu)
    resolved = _GPU_ALIAS_TO_RESOLVED.get(alias, GPU_CONFIG)
    function_name = _GPU_FUNCTION_NAMES.get(alias)
    if requested_gpu:
        print(
            f"🚀 Dispatching render (requested '{requested_gpu}') to GPU '{alias}' ({resolved})"
        )
    else:
        print(f"🚀 Dispatching render to default GPU '{alias}' ({resolved})")
    try:
        return function.remote(spec_dict, bundle_b64)
    except modal.exception.ExecutionError as exc:
        if function_name and "has not been hydrated" in str(exc):
            print(
                f"♻️ GPU function '{function_name}' not hydrated in this container; looking up dynamically"
            )
            try:
                lookup_fn = modal.Function.from_name(APP_NAME, function_name)
            except modal.exception.NotFoundError:
                print(
                    f"⚠️ Function '{function_name}' not found in app '{APP_NAME}'; retrying with default GPU '{_DEFAULT_GPU_ALIAS}'"
                )
                if alias == _DEFAULT_GPU_ALIAS:
                    raise
                return render_reel_default.remote(spec_dict, bundle_b64)
            return lookup_fn.remote(spec_dict, bundle_b64)
        raise


@app.function(
    image=image,
    timeout=ENTRYPOINT_TIMEOUT_SECONDS,
    memory=2048,
    secrets=[_render_secret],
)
def render_reel(spec_dict: dict, bundle_b64: str) -> dict[str, object]:
    """Entry point that routes to the appropriate GPU-backed render function."""

    return render_reel_for_request(spec_dict, bundle_b64)


@app.function(image=image)
@modal.asgi_app()
def render_endpoint():
    """FastAPI endpoint for POST /render."""

    from fastapi import FastAPI

    web_app = FastAPI()

    @web_app.post("/render")
    async def render(data: dict):
        spec = data.get("spec")
        bundle_b64 = data.get("bundle_b64")
        if not spec or not bundle_b64:
            return {"error": "Missing 'spec' or 'bundle_b64'"}
        return render_reel_for_request(spec, bundle_b64)

    return web_app


@app.local_entrypoint()
def main():
    """Test the ffmpeg function locally."""

    print("🧪 Testing ffmpeg function...")
    result = test_ffmpeg.remote()
    if result.get("success"):
        print(f"✅ Success! Video size: {result['size_bytes']} bytes")
        output_path = Path("test_output.mp4")
        video_bytes = base64.b64decode(result["video_b64"])
        output_path.write_bytes(video_bytes)
        print(f"💾 Saved to: {output_path}")
    else:
        print(f"❌ Failed: {result.get('error')}")
