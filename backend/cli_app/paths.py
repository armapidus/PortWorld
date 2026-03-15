from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_REPO_MARKERS: tuple[str, ...] = (
    "backend/Dockerfile",
    "backend/.env.example",
    "docker-compose.yml",
)


class ProjectRootResolutionError(RuntimeError):
    """Raised when the PortWorld project root cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    project_root: Path
    backend_dir: Path
    env_file: Path
    env_example_file: Path
    dockerfile: Path
    compose_file: Path
    cli_dir: Path
    project_config_file: Path
    cli_state_dir: Path
    gcp_cloud_run_state_file: Path

    @classmethod
    def from_root(cls, project_root: Path) -> "ProjectPaths":
        root = project_root.resolve()
        return cls(
            project_root=root,
            backend_dir=root / "backend",
            env_file=root / "backend" / ".env",
            env_example_file=root / "backend" / ".env.example",
            dockerfile=root / "backend" / "Dockerfile",
            compose_file=root / "docker-compose.yml",
            cli_dir=root / ".portworld",
            project_config_file=root / ".portworld" / "project.json",
            cli_state_dir=root / ".portworld" / "state",
            gcp_cloud_run_state_file=root / ".portworld" / "state" / "gcp-cloud-run.json",
        )

    def missing_required_markers(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.dockerfile.is_file():
            missing.append("backend/Dockerfile")
        if not self.env_example_file.is_file():
            missing.append("backend/.env.example")
        if not self.compose_file.is_file():
            missing.append("docker-compose.yml")
        return tuple(missing)

    def validate_required_markers(self) -> None:
        missing = self.missing_required_markers()
        if missing:
            missing_list = ", ".join(missing)
            raise ProjectRootResolutionError(
                f"{self.project_root} is not a valid PortWorld project root. "
                f"Missing required files: {missing_list}."
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "project_root": str(self.project_root),
            "backend_dir": str(self.backend_dir),
            "env_file": str(self.env_file),
            "env_example_file": str(self.env_example_file),
            "dockerfile": str(self.dockerfile),
            "compose_file": str(self.compose_file),
            "cli_dir": str(self.cli_dir),
            "project_config_file": str(self.project_config_file),
            "cli_state_dir": str(self.cli_state_dir),
            "gcp_cloud_run_state_file": str(self.gcp_cloud_run_state_file),
        }


def resolve_project_paths(*, explicit_root: Path | None = None, start: Path | None = None) -> ProjectPaths:
    if explicit_root is not None:
        paths = ProjectPaths.from_root(explicit_root)
        paths.validate_required_markers()
        return paths

    current = (start or Path.cwd()).resolve()
    candidates = (current,) + tuple(current.parents)
    for candidate in candidates:
        paths = ProjectPaths.from_root(candidate)
        if not paths.missing_required_markers():
            return paths

    markers = ", ".join(REQUIRED_REPO_MARKERS)
    raise ProjectRootResolutionError(
        "Could not find the PortWorld project root from the current directory. "
        f"Expected to find: {markers}. Use --project-root to point at the repo root."
    )
