# Contributing to ReelToolkit Renderer

Thanks for taking the time to improve this project! Below is a quick guide to get you started.

## 🛠 Development setup

1. Clone the repo and install dependencies:
   ```bash
   git clone https://github.com/<your-org>/reeltoolkit-renderer.git
   cd reeltoolkit-renderer
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -e .[dev]
   ```
2. Run the test suite:
   ```bash
   pytest
   ```
3. Use `ruff` (`pip install ruff`) to lint your changes:
   ```bash
   ruff check .
   ```

## 💡 Workflow

- Create a feature branch (`git checkout -b feature/my-change`).
- Commit with clear messages, referencing issues when possible.
- Open a pull request against `main` and fill in the template (if available).
- Ensure all GitHub Actions checks pass before requesting review.

## 🧪 Testing guidelines

- Add unit tests for new features or bug fixes.
- Keep tests deterministic: avoid network calls and use fixtures/mocks.
- Prefer `pytest.mark.asyncio` for async functions.

## 📝 Code style

- Follow PEP 8 conventions; rely on Ruff to catch most issues.
- Type hints are encouraged.
- Keep functions small and focused.

## 📄 Documentation

- Update the README or relevant docs when behavior changes.
- Provide examples or usage notes for new public APIs.

## 🛡 Security

- Do not commit secrets or API keys. Use environment variables instead.
- Report vulnerabilities privately via security@reeltoolkit.com (placeholder).

Thank you for helping build a better ReelToolkit Renderer! 💙
