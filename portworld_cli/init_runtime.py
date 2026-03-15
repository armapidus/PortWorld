from __future__ import annotations

from dataclasses import dataclass

import click

from portworld_cli.config_runtime import (
    CloudEditOptions,
    ConfigRuntimeError,
    ProviderEditOptions,
    SecurityEditOptions,
    apply_cloud_section,
    apply_provider_section,
    apply_security_section,
    build_init_review_lines,
    build_init_success_message,
    collect_cloud_section,
    collect_provider_section,
    collect_security_section,
    confirm_apply,
    load_config_session,
    preview_secret_readiness,
    write_config_artifacts,
)
from portworld_cli.output import CommandResult, DiagnosticCheck
from portworld_cli.paths import ProjectRootResolutionError
from portworld_cli.project_config import ProjectConfigError
from portworld_cli.state import CLIStateDecodeError, CLIStateTypeError
from portworld_cli.envfile import EnvFileParseError
from portworld_cli.context import CLIContext


COMMAND_NAME = "portworld init"


@dataclass(frozen=True, slots=True)
class InitOptions:
    force: bool
    with_vision: bool
    without_vision: bool
    with_tooling: bool
    without_tooling: bool
    openai_api_key: str | None
    vision_provider_api_key: str | None
    tavily_api_key: str | None
    backend_profile: str | None
    cors_origins: str | None
    allowed_hosts: str | None
    bearer_token: str | None
    generate_bearer_token: bool
    clear_bearer_token: bool
    project_mode: str | None
    project: str | None
    region: str | None
    service: str | None
    artifact_repo: str | None
    sql_instance: str | None
    database: str | None
    bucket: str | None
    min_instances: int | None
    max_instances: int | None
    concurrency: int | None
    cpu: str | None
    memory: str | None


def run_init(cli_context: CLIContext, options: InitOptions) -> CommandResult:
    try:
        session = load_config_session(cli_context)

        provider_result = collect_provider_section(
            session,
            ProviderEditOptions(
                with_vision=options.with_vision,
                without_vision=options.without_vision,
                with_tooling=options.with_tooling,
                without_tooling=options.without_tooling,
                openai_api_key=options.openai_api_key,
                vision_provider_api_key=options.vision_provider_api_key,
                tavily_api_key=options.tavily_api_key,
            ),
        )
        project_config, env_updates = apply_provider_section(
            session.project_config,
            provider_result,
        )

        security_result = collect_security_section(
            _session_with_project_config(session, project_config),
            SecurityEditOptions(
                backend_profile=options.backend_profile,
                cors_origins=options.cors_origins,
                allowed_hosts=options.allowed_hosts,
                bearer_token=options.bearer_token,
                generate_bearer_token=options.generate_bearer_token,
                clear_bearer_token=options.clear_bearer_token,
            ),
        )
        project_config, security_env_updates = apply_security_section(
            project_config,
            security_result,
        )
        env_updates.update(security_env_updates)

        cloud_result = collect_cloud_section(
            _session_with_project_config(session, project_config),
            CloudEditOptions(
                project_mode=options.project_mode,
                project=options.project,
                region=options.region,
                service=options.service,
                artifact_repo=options.artifact_repo,
                sql_instance=options.sql_instance,
                database=options.database,
                bucket=options.bucket,
                min_instances=options.min_instances,
                max_instances=options.max_instances,
                concurrency=options.concurrency,
                cpu=options.cpu,
                memory=options.memory,
            ),
            prompt_defaults_when_local=False,
        )
        project_config, cloud_env_updates = apply_cloud_section(project_config, cloud_result)
        env_updates.update(cloud_env_updates)

        preview_outcome = preview_secret_readiness(session, project_config, env_updates)
        confirm_apply(
            cli_context,
            command_name=COMMAND_NAME,
            env_path=session.project_paths.env_file,
            project_config_path=session.project_paths.project_config_file,
            summary_lines=build_init_review_lines(
                project_config=project_config,
                secret_readiness=preview_outcome,
            ),
            force=options.force,
        )
        outcome = write_config_artifacts(session, project_config, env_updates)
    except ProjectRootResolutionError as exc:
        return _failure_result(exc, exit_code=1)
    except (
        CLIStateDecodeError,
        CLIStateTypeError,
        ConfigRuntimeError,
        EnvFileParseError,
        ProjectConfigError,
    ) as exc:
        return _failure_result(exc, exit_code=2)
    except click.Abort:
        return CommandResult(
            ok=False,
            command=COMMAND_NAME,
            message="Aborted; configuration changes were not applied.",
            data={"status": "aborted", "error_type": "Abort"},
            exit_code=1,
        )
    except Exception as exc:
        return _failure_result(exc, exit_code=1)

    checks: list[DiagnosticCheck] = []
    if (
        outcome.project_config.providers.tooling.enabled
        and not outcome.secret_readiness.tavily_api_key_present
    ):
        checks.append(
            DiagnosticCheck(
                id="missing-tavily-api-key",
                status="warn",
                message="tavily-api-key is not configured yet.",
                action="Run `portworld config edit providers` to add the missing optional credential.",
            )
        )

    return CommandResult(
        ok=True,
        command=COMMAND_NAME,
        message=build_init_success_message(
            project_config=outcome.project_config,
            secret_readiness=outcome.secret_readiness,
            env_path=outcome.env_write_result.env_path,
            project_config_path=session.project_paths.project_config_file,
            backup_path=outcome.env_write_result.backup_path,
        ),
        data={
            "project_root": str(session.project_paths.project_root),
            "project_config_path": str(session.project_paths.project_config_file),
            "env_path": str(outcome.env_write_result.env_path),
            "backup_path": (
                str(outcome.env_write_result.backup_path)
                if outcome.env_write_result.backup_path
                else None
            ),
            "project_config": outcome.project_config.to_payload(),
            "secret_readiness": outcome.secret_readiness.to_dict(),
        },
        checks=tuple(checks),
        exit_code=0,
    )
def _session_with_project_config(session, project_config):
    return type(session)(
        cli_context=session.cli_context,
        project_paths=session.project_paths,
        template=session.template,
        existing_env=session.existing_env,
        project_config=project_config,
        derived_from_legacy=session.derived_from_legacy,
        remembered_deploy_state=session.remembered_deploy_state,
    )


def _failure_result(exc: Exception, *, exit_code: int) -> CommandResult:
    return CommandResult(
        ok=False,
        command=COMMAND_NAME,
        message=str(exc),
        data={
            "status": "error",
            "error_type": type(exc).__name__,
        },
        exit_code=exit_code,
    )
