from __future__ import annotations

import click

from backend.cli_app.commands.common import raise_not_implemented


@click.group("deploy")
def deploy_group() -> None:
    """Deploy PortWorld to a managed target."""


@deploy_group.command("gcp-cloud-run")
def deploy_gcp_cloud_run_command() -> None:
    """Deploy PortWorld backend to GCP Cloud Run."""
    raise_not_implemented("portworld deploy gcp-cloud-run")
