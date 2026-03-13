from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented


@click.group("ops")
def ops_group() -> None:
    """Run backend operator tasks."""


@ops_group.command("check-config")
def check_config_command() -> None:
    """Validate backend configuration."""
    raise_not_implemented("portworld ops check-config")


@ops_group.command("bootstrap-storage")
def bootstrap_storage_command() -> None:
    """Create storage directories and schema."""
    raise_not_implemented("portworld ops bootstrap-storage")


@ops_group.command("export-memory")
def export_memory_command() -> None:
    """Export backend memory artifacts."""
    raise_not_implemented("portworld ops export-memory")


@ops_group.command("migrate-storage-layout")
def migrate_storage_layout_command() -> None:
    """Migrate legacy storage layout artifacts."""
    raise_not_implemented("portworld ops migrate-storage-layout")
