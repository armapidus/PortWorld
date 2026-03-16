from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from portworld_cli.paths import ProjectPaths, WorkspacePaths, resolve_project_paths, resolve_workspace_paths


@dataclass(slots=True)
class CLIContext:
    project_root_override: Path | None
    verbose: bool
    json_output: bool
    non_interactive: bool
    yes: bool
    _resolved_project_paths: ProjectPaths | None = field(default=None, init=False, repr=False)
    _resolved_workspace_paths: WorkspacePaths | None = field(default=None, init=False, repr=False)

    def resolve_project_paths(self) -> ProjectPaths:
        if self._resolved_project_paths is None:
            if self._resolved_workspace_paths is not None and self._resolved_workspace_paths.source_project_paths is not None:
                self._resolved_project_paths = self._resolved_workspace_paths.source_project_paths
            else:
                self._resolved_project_paths = resolve_project_paths(
                    explicit_root=self.project_root_override,
                )
        return self._resolved_project_paths

    def resolve_workspace_paths(self) -> WorkspacePaths:
        if self._resolved_workspace_paths is None:
            self._resolved_workspace_paths = resolve_workspace_paths(
                explicit_root=self.project_root_override,
            )
            if self._resolved_workspace_paths.source_project_paths is not None:
                self._resolved_project_paths = self._resolved_workspace_paths.source_project_paths
        return self._resolved_workspace_paths
