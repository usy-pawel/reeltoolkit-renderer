"""Subtitle helpers used by the render pipeline."""

from __future__ import annotations

import os
import re
from typing import Dict, List

from moviepy import AudioFileClip


def _ass_header(width: int, height: int) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Karaoke, Arial, 48, &H00FFFFFF, &H0000FFFF, &H00000000, &H64000000, 0, 0, 0, 0, 100, 100, 0, 0, 3, 2, 0.5, 2, 50, 50, 120, 0\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours = centiseconds // 360000
    centiseconds %= 360000
    minutes = centiseconds // 6000
    centiseconds %= 6000
    secs = centiseconds // 100
    centiseconds %= 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def generate_ass_karaoke(
    segments: List[Dict],
    out_path: str,
    width: int,
    height: int,
) -> None:
    current = 0.0
    enriched = []
    for seg in segments:
        text_value = str(seg.get("text", "") or "").strip()
        subtitle_enabled = bool(seg.get("subtitle", True))
        if not subtitle_enabled:
            current += max(1.0, len(text_value) * 0.06)
            continue
        audio_path = seg.get("audio_path")
        if audio_path:
            with AudioFileClip(audio_path) as clip:
                duration = clip.duration
        else:
            duration = max(1.0, len(text_value) * 0.06)
        start = current
        end = current + duration
        current = end
        enriched.append({"start": start, "end": end, "text": text_value})

    lines = [_ass_header(width, height)]

    for seg in enriched:
        if not seg["text"]:
            continue
        total_cs = max(1, int(round((seg["end"] - seg["start"]) * 100)))
        words = re.findall(r"\S+", seg["text"]) or [seg["text"]]
        lengths = [max(1, len(re.sub(r"\W", "", w))) for w in words]
        total_len = sum(lengths) or len(words)
        allocations = [max(1, int(round(total_cs * l / total_len))) for l in lengths]
        diff = total_cs - sum(allocations)
        if diff:
            allocations[-1] += diff
        parts = [f"{{\\k{cs}}}{_ass_escape(word)}" for word, cs in zip(words, allocations)]
        line = (
            "Dialogue: 0,"
            f"{_ass_time(seg['start'])},{_ass_time(seg['end'])},"
            "Karaoke,,0,0,0,,"
            + " ".join(parts)
        )
        lines.append(line)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
