from __future__ import annotations

from portworld_cli.context import CLIContext
from portworld_cli.output import CommandResult
from portworld_cli.project_config import RUNTIME_SOURCE_PUBLISHED, RUNTIME_SOURCE_SOURCE
from portworld_cli.services.config import (
    CloudEditOptions,
    CloudSectionResult,
    ConfigRuntimeError,
    ConfigUsageError,
    ConfigValidationError,
    ConfigWriteOutcome,
    ProviderEditOptions,
    ProviderSectionResult,
    SecurityEditOptions,
    SecuritySectionResult,
    apply_cloud_section,
    apply_provider_section,
    apply_security_section,
    build_config_show_message,
    build_init_review_lines,
    build_init_success_message,
    build_section_success_message,
    collect_cloud_section,
    collect_provider_section,
    collect_security_section,
    confirm_apply,
    preview_secret_readiness,
    write_config_artifacts,
)
from portworld_cli.services.config.edit_service import (
    run_edit_cloud as _run_edit_cloud,
    run_edit_providers as _run_edit_providers,
    run_edit_security as _run_edit_security,
)
from portworld_cli.services.config.show_service import run_config_show as _run_config_show
from portworld_cli.workspace.session import (
    SecretReadiness,
    WorkspaceSession as ConfigSession,
    load_workspace_session,
    require_source_workspace_session,
)


# Compatibility facade: this module preserves existing imports while delegating
# config command behavior to portworld_cli.services.config and session loading
# to portworld_cli.workspace.session.

def load_config_session(cli_context: CLIContext) -> ConfigSession:
    return load_workspace_session(cli_context)


def ensure_source_runtime_session(
    session: ConfigSession,
    *,
    command_name: str,
    requested_runtime_source: str | None = None,
) -> ConfigSession:
    return require_source_workspace_session(
        session,
        command_name=command_name,
        requested_runtime_source=requested_runtime_source,
        usage_error_type=ConfigUsageError,
    )


def run_config_show(cli_context: CLIContext) -> CommandResult:
    return _run_config_show(cli_context)


def run_edit_providers(cli_context: CLIContext, options: ProviderEditOptions) -> CommandResult:
    return _run_edit_providers(cli_context, options)


def run_edit_security(cli_context: CLIContext, options: SecurityEditOptions) -> CommandResult:
    return _run_edit_security(cli_context, options)


def run_edit_cloud(cli_context: CLIContext, options: CloudEditOptions) -> CommandResult:
    return _run_edit_cloud(cli_context, options)


__all__ = (
    "CloudEditOptions",
    "CloudSectionResult",
    "ConfigRuntimeError",
    "ConfigSession",
    "ConfigUsageError",
    "ConfigValidationError",
    "ConfigWriteOutcome",
    "ProviderEditOptions",
    "ProviderSectionResult",
    "RUNTIME_SOURCE_PUBLISHED",
    "RUNTIME_SOURCE_SOURCE",
    "SecretReadiness",
    "SecurityEditOptions",
    "SecuritySectionResult",
    "apply_cloud_section",
    "apply_provider_section",
    "apply_security_section",
    "build_config_show_message",
    "build_init_review_lines",
    "build_init_success_message",
    "build_section_success_message",
    "collect_cloud_section",
    "collect_provider_section",
    "collect_security_section",
    "confirm_apply",
    "ensure_source_runtime_session",
    "load_config_session",
    "preview_secret_readiness",
    "run_config_show",
    "run_edit_cloud",
    "run_edit_providers",
    "run_edit_security",
    "write_config_artifacts",
)
