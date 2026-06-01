from pathlib import Path
import tomllib


def test_uv_project_metadata() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())

    assert data["project"]["name"] == "clawake"
    assert data["project"]["readme"] == "README.md"
    assert sorted(data["dependency-groups"]["dev"]) == [
        "pytest>=8.4.0",
        "ruff>=0.12.0",
    ]
