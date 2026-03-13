from __future__ import annotations

from backend.cli_app.context import CLIContext
from backend.cli_app.output import CommandResult, exit_with_result


SPEC_DOC_PATH = "docs/roadmap/backend/BACKEND_CLI_SPEC.md"
IMPLEMENTATION_PLAN_DOC_PATH = "docs/roadmap/backend/BACKEND_CLI_IMPLEMENTATION_PLAN.md"
DOC_HINT = f"See {SPEC_DOC_PATH} and {IMPLEMENTATION_PLAN_DOC_PATH}."


def not_implemented_result(command_path: str) -> CommandResult:
    return CommandResult(
        ok=False,
        command=command_path,
        message=f"'{command_path}' is not implemented yet. {DOC_HINT}",
        data={
            "docs": {
                "spec": SPEC_DOC_PATH,
                "implementation_plan": IMPLEMENTATION_PLAN_DOC_PATH,
            }
        },
        exit_code=1,
    )


def raise_not_implemented(cli_context: CLIContext, command_path: str) -> None:
    exit_with_result(cli_context, not_implemented_result(command_path))
