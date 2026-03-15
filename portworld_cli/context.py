from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from portworld_cli.paths import ProjectPaths, resolve_project_paths


@dataclass(slots=True)
class CLIContext:
    project_root_override: Path | None
    verbose: bool
    json_output: bool
    non_interactive: bool
    yes: bool
    _resolved_project_paths: ProjectPaths | None = field(default=None, init=False, repr=False)

    def resolve_project_paths(self) -> ProjectPaths:
        if self._resolved_project_paths is None:
            self._resolved_project_paths = resolve_project_paths(
                explicit_root=self.project_root_override,
            )
        return self._resolved_project_paths
