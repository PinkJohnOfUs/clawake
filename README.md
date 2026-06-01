# clawake
The sewer system beneath the bowls on which the agents are sitting

## Development

This repository now uses `uv` for dependency management and local tooling.

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```
