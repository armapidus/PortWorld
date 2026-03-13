from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented
from backend.cli_app.context import CLIContext


@click.command("doctor")
@click.pass_obj
def doctor_command(cli_context: CLIContext) -> None:
    """Validate local or managed deployment readiness."""
    raise_not_implemented(cli_context, "portworld doctor")
