from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented
from backend.cli_app.context import CLIContext


@click.group("ops")
def ops_group() -> None:
    """Run backend operator tasks."""


@ops_group.command("check-config")
@click.pass_obj
def check_config_command(cli_context: CLIContext) -> None:
    """Validate backend configuration."""
    raise_not_implemented(cli_context, "portworld ops check-config")


@ops_group.command("bootstrap-storage")
@click.pass_obj
def bootstrap_storage_command(cli_context: CLIContext) -> None:
    """Create storage directories and schema."""
    raise_not_implemented(cli_context, "portworld ops bootstrap-storage")


@ops_group.command("export-memory")
@click.pass_obj
def export_memory_command(cli_context: CLIContext) -> None:
    """Export backend memory artifacts."""
    raise_not_implemented(cli_context, "portworld ops export-memory")


@ops_group.command("migrate-storage-layout")
@click.pass_obj
def migrate_storage_layout_command(cli_context: CLIContext) -> None:
    """Migrate legacy storage layout artifacts."""
    raise_not_implemented(cli_context, "portworld ops migrate-storage-layout")
