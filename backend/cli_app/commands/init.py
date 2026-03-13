from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented


@click.command("init")
def init_command() -> None:
    """Initialize local PortWorld backend configuration."""
    raise_not_implemented("portworld init")
