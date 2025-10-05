"""Audio mixing helpers using FFmpeg."""

from __future__ import annotations

import contextlib
import os
import subprocess


async def mix_background_music(
    video_in: str,
    music_in: str,
    video_out: str,
    *,
    volume: float = 0.15,
    duck: bool = False,
) -> None:
    os.makedirs(os.path.dirname(video_out), exist_ok=True)

    if duck:
        afilter = (
            f"[1:a]volume={volume}[bg];"
            f"[0:a][bg]sidechaincompress=threshold=0.03:ratio=6:attack=5:release=250:makeup=0[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "0:v", "-map", "[m]"]
    else:
        afilter = (
            f"[1:a]volume={volume}[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "0:v", "-map", "[m]"]

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_in,
        "-i",
        music_in,
        *audio_map,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        video_out,
    ]
    subprocess.run(cmd, check=True)


async def mix_slide_audio(
    voice_in: str,
    music_in: str,
    out_audio: str,
    *,
    duration: float,
    volume: float = 0.15,
    duck: bool = False,
) -> None:
    temp_music = out_audio + ".music.tmp.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            music_in,
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "mp3",
            temp_music,
        ],
        check=True,
    )

    fade = max(0.15, min(0.6, duration * 0.1))
    if duck:
        afilter = (
            f"[1:a]afade=t=in:ss=0:d={fade},"
            f"afade=t=out:st={max(0.0, duration-fade):.3f}:d={fade},"
            f"volume={volume}[bg];"
            f"[0:a][bg]sidechaincompress=threshold=0.03:ratio=6:attack=5:release=250:makeup=0[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "[m]"]
    else:
        afilter = (
            f"[1:a]afade=t=in:ss=0:d={fade},"
            f"afade=t=out:st={max(0.0, duration-fade):.3f}:d={fade},"
            f"volume={volume}[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "[m]"]

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                voice_in,
                "-i",
                temp_music,
                *audio_map,
                "-c:a",
                "mp3",
                "-b:a",
                "128k",
                "-ar",
                "48000",
                out_audio,
            ],
            check=True,
        )
    finally:
        with contextlib.suppress(Exception):
            os.remove(temp_music)


async def mix_background_music_masked(
    video_in: str,
    music_in: str,
    video_out: str,
    *,
    volume: float,
    duck: bool,
    mute_ranges: list[tuple[float, float]] | None,
) -> None:
    if mute_ranges:
        conditions = [f"between(t,{start:.3f},{end:.3f})" for start, end in mute_ranges]
        expression = f"{volume}*if({'+'.join(conditions)},0,1)"
    else:
        expression = f"{volume}"

    if duck:
        afilter = (
            f"[1:a]volume={expression}[bg];"
            f"[0:a][bg]sidechaincompress=threshold=0.03:ratio=6:attack=5:release=250:makeup=0[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "0:v", "-map", "[m]"]
    else:
        afilter = (
            f"[1:a]volume={expression}[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[m]"
        )
        audio_map = ["-filter_complex", afilter, "-map", "0:v", "-map", "[m]"]

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_in,
            "-i",
            music_in,
            *audio_map,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            video_out,
        ],
        check=True,
    )
