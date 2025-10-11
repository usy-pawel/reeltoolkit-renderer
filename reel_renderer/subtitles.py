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
    lines = [_ass_header(width, height)]

    grouped: dict[int, list[dict]] = {}
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue

        raw_text = str(seg.get("text", "") or "")
        trimmed_text = raw_text.strip()
        subtitle_enabled = bool(seg.get("subtitle", True))

        slide_idx = seg.get("slide_index")
        if slide_idx is None:
            slide_idx = seg.get("slide")
        if slide_idx is None:
            slide_idx = seg.get("index")
        try:
            slide_idx = int(slide_idx)
        except (TypeError, ValueError):
            slide_idx = idx

        chunk_idx = seg.get("chunk_index", idx)
        try:
            chunk_idx = int(chunk_idx)
        except (TypeError, ValueError):
            chunk_idx = idx

        raw_lines = seg.get("lines")
        normalized_lines: list[str] = []
        if isinstance(raw_lines, list):
            for line in raw_lines:
                candidate = str(line or "").strip()
                if candidate:
                    normalized_lines.append(candidate)
        if not normalized_lines and trimmed_text:
            normalized_lines = [part.strip() for part in raw_text.splitlines() if part.strip()]
        if not normalized_lines and trimmed_text:
            normalized_lines = [trimmed_text]

        duration_value = seg.get("duration")
        try:
            duration = float(duration_value) if duration_value is not None else None
        except (TypeError, ValueError):
            duration = None

        start_rel = seg.get("start")
        try:
            start_rel = float(start_rel) if start_rel is not None else 0.0
        except (TypeError, ValueError):
            start_rel = 0.0

        end_rel = seg.get("end")
        try:
            end_rel = float(end_rel) if end_rel is not None else None
        except (TypeError, ValueError):
            end_rel = None

        if duration is None and end_rel is not None:
            duration = max(0.0, end_rel - start_rel)

        if duration is None:
            audio_path = seg.get("audio_path")
            if audio_path:
                with AudioFileClip(audio_path) as clip:
                    duration = clip.duration
            else:
                duration = max(1.0, len(trimmed_text) * 0.06)

        if end_rel is None:
            end_rel = start_rel + duration

        if not isinstance(duration, float) or not duration or duration <= 0:
            duration = max(0.5, len(trimmed_text) * 0.06 or 1.0)

        grouped.setdefault(slide_idx, []).append(
            {
                "chunk_index": chunk_idx,
                "text": trimmed_text,
                "lines": normalized_lines,
                "subtitle": subtitle_enabled,
                "duration": float(duration),
                "start": float(start_rel),
                "end": float(end_rel),
                "subtitle_vertical_position": seg.get("subtitle_vertical_position"),
            }
        )

    timeline_offset = 0.0

    for slide_idx in sorted(grouped.keys()):
        slide_segments = grouped[slide_idx]
        slide_segments.sort(key=lambda item: item["chunk_index"])
        slide_length = 0.0

        for entry in slide_segments:
            slide_length = max(slide_length, entry["end"])
            if not entry["subtitle"]:
                continue
            if not entry["text"]:
                continue

            chunk_start = timeline_offset + max(0.0, entry["start"])
            chunk_end = timeline_offset + max(chunk_start, entry["end"])
            chunk_duration = max(0.01, chunk_end - chunk_start)

            line_groups: list[list[str]] = []
            for line_text in entry["lines"]:
                tokens = re.findall(r"\S+", line_text)
                if tokens:
                    line_groups.append(tokens)

            if not line_groups:
                fallback_token = entry["text"] or ""
                if not fallback_token:
                    continue
                line_groups = [[fallback_token]]

            words = [token for group in line_groups for token in group]
            lengths = [max(1, len(re.sub(r"\W", "", token))) for token in words]
            total_len = sum(lengths) or len(words) or 1
            total_cs = max(1, int(round(chunk_duration * 100)))
            alloc = [max(1, int(round(total_cs * length / total_len))) for length in lengths]
            diff = total_cs - sum(alloc)
            if diff != 0:
                alloc[-1] += diff

            karaoke_parts: list[str] = []
            alloc_idx = 0
            for line_idx, tokens in enumerate(line_groups):
                for token_idx, token in enumerate(tokens):
                    cs_value = alloc[min(alloc_idx, len(alloc) - 1)]
                    alloc_idx += 1
                    karaoke_parts.append(f"{{\\k{cs_value}}}{_ass_escape(token)}")
                    if token_idx < len(tokens) - 1:
                        karaoke_parts.append(" ")
                if line_idx < len(line_groups) - 1:
                    karaoke_parts.append(r"\N")

            kara_text = "".join(karaoke_parts)

            margin_v = 120
            raw_position = entry.get("subtitle_vertical_position")
            if isinstance(raw_position, (int, float)):
                clamped = max(0.0, min(100.0, float(raw_position)))
                top_px = clamped * height / 100.0
                margin_px = height - top_px
                margin_v = max(0, min(int(round(margin_px)), height))

            dialogue_line = (
                f"Dialogue: 0,{_ass_time(chunk_start)},{_ass_time(chunk_end)},"
                f"Karaoke,,0,0,{margin_v},,{kara_text}"
            )
            lines.append(dialogue_line)

        if slide_length <= 0:
            slide_length = sum(entry["duration"] for entry in slide_segments)
        timeline_offset += max(0.0, slide_length)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
