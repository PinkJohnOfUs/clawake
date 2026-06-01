from pathlib import Path

from typer.testing import CliRunner

from clawake.cli import app

runner = CliRunner()


def test_validate_command() -> None:
    result = runner.invoke(app, ["validate", "--config", str(Path("examples/inventory/dev.yaml"))])
    assert result.exit_code == 0
    assert "is valid" in result.stdout
