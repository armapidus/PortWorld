from __future__ import annotations

import click


DOC_HINT = (
    "See docs/BACKEND_CLI_SPEC.md and "
    "docs/roadmap/backend/BACKEND_CLI_IMPLEMENTATION_PLAN.md."
)


def raise_not_implemented(command_path: str) -> None:
    raise click.ClickException(
        f"'{command_path}' is not implemented yet. {DOC_HINT}"
    )
