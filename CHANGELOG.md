# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.18] - 2024-11-24
### Added
- Slide-level transform support (scale and XY offsets) throughout the render pipeline.
- Automatic fallback to the MoviePy renderer when transforms are present, with regression coverage.
- Modal GPU alias handling and hydration retries for cold deployments.

### Changed
- Preserve source resolution for `final` quality renders while continuing to downscale `draft` jobs.
- Default Modal GPU preset updated to L4 with refreshed price estimates.
- Modal GPU and entrypoint timeouts are now configurable via environment variables with smarter defaults.
- Documentation for Modal deployment reflects new timeout configuration options.

### Removed
- Legacy binary MP4 fixtures no longer required by the test suite.

[0.1.18]: https://github.com/<your-org>/reeltoolkit-renderer/releases/tag/0.1.18
