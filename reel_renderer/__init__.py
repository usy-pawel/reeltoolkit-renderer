"""Public API for the reel_renderer pipeline - LAZY IMPORTS ONLY."""

# Only import lightweight types - NOT rendering modules
from .types import RenderJobSpec

__all__ = ["RenderJobSpec"]

