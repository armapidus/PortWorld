from __future__ import annotations

from typing import TYPE_CHECKING

from portworld_cli.deploy.config import (
    DeployGCPCloudRunOptions,
    DeployStageError,
    DeployUsageError,
    ResolvedDeployConfig,
)

if TYPE_CHECKING:
    from portworld_cli.context import CLIContext
    from portworld_cli.output import CommandResult


# Compatibility facade: keep historical deploy_runtime imports stable while
# deploy orchestration lives in portworld_cli.deploy.* modules.


def run_deploy_gcp_cloud_run(
    cli_context: CLIContext,
    options: DeployGCPCloudRunOptions,
) -> CommandResult:
    from portworld_cli.deploy.service import run_deploy_gcp_cloud_run as _run

    return _run(cli_context, options)


__all__ = [
    "DeployGCPCloudRunOptions",
    "DeployStageError",
    "DeployUsageError",
    "ResolvedDeployConfig",
    "run_deploy_gcp_cloud_run",
]
