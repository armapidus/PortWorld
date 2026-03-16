from __future__ import annotations

from portworld_cli.context import CLIContext
from portworld_cli.workspace.session import (
    InspectionSession,
    ResolvedGCPInspectionTarget,
    load_inspection_session as _load_inspection_session,
    resolve_gcp_inspection_target as _resolve_gcp_inspection_target,
)


def load_inspection_session(cli_context: CLIContext) -> InspectionSession:
    return _load_inspection_session(cli_context)


def resolve_gcp_inspection_target(
    session: InspectionSession,
    *,
    project_id: str | None = None,
    region: str | None = None,
    service_name: str | None = None,
) -> ResolvedGCPInspectionTarget:
    return _resolve_gcp_inspection_target(
        session,
        project_id=project_id,
        region=region,
        service_name=service_name,
    )
