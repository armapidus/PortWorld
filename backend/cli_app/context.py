from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CLIContext:
    project_root: Path | None
    verbose: bool
    json_output: bool
    non_interactive: bool
    yes: bool
