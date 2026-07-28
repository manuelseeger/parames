# Coding Standards

- Target Python 3.13 and manage dependencies and commands with `uv`.
- Prefer small, focused modules and straightforward control flow over new abstractions.
- Use type hints for public interfaces and Pydantic models for validated data boundaries.
- Keep configuration and secrets in settings or environment variables; never log credentials.
- Preserve established FastAPI, service, persistence, and plugin boundaries.
- Add focused `pytest` coverage for changed behavior; use Arrange–Act–Assert and descriptive `test_*` names.
- Run tests with `PARAMES_DEV_MODE=true`; run the full suite before completion.
- Use conventional commit messages.
