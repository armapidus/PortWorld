from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented
from backend.cli_app.context import CLIContext


@click.command("init")
@click.pass_obj
def init_command(cli_context: CLIContext) -> None:
    """Initialize local PortWorld backend configuration."""
    raise_not_implemented(cli_context, "portworld init")
