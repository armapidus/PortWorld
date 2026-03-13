from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented
from backend.cli_app.context import CLIContext


@click.group("deploy")
def deploy_group() -> None:
    """Deploy PortWorld to a managed target."""


@deploy_group.command("gcp-cloud-run")
@click.pass_obj
def deploy_gcp_cloud_run_command(cli_context: CLIContext) -> None:
    """Deploy PortWorld backend to GCP Cloud Run."""
    raise_not_implemented(cli_context, "portworld deploy gcp-cloud-run")
