from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented


@click.command("doctor")
def doctor_command() -> None:
    """Validate local or managed deployment readiness."""
    raise_not_implemented("portworld doctor")
