"""Public API for the :mod:`reel_renderer` package.

Keep imports lightweight at module load time; pull heavy rendering code lazily.
"""

from __future__ import annotations

from typing import Any

from .types import RenderJobSpec

# Pillow 10 removed Image.ANTIALIAS; patch it back for moviepy compatibility.
try:  # pragma: no cover - best-effort shim
	from PIL import Image as _PILImage

	if "ANTIALIAS" not in vars(_PILImage) and hasattr(_PILImage, "Resampling"):
		_PILImage.ANTIALIAS = _PILImage.Resampling.LANCZOS  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Pillow optional
	_PILImage = None  # type: ignore[assignment]


def render_reel(*args: Any, **kwargs: Any):
	"""Lazily import and delegate to the full render pipeline."""

	from .pipeline import render_reel as _render_reel

	return _render_reel(*args, **kwargs)


__all__ = ["RenderJobSpec", "render_reel"]

