from __future__ import annotations

from dataclasses import dataclass

from portworld_cli.gcp.executor import GCloudExecutor
from portworld_cli.gcp.types import GCPResult, MutationOutcome


@dataclass(frozen=True, slots=True)
class ArtifactRepositoryRef:
    project_id: str
    region: str
    repository: str
    format: str


class ArtifactRegistryAdapter:
    def __init__(self, executor: GCloudExecutor) -> None:
        self._executor = executor

    def get_repository(
        self,
        *,
        project_id: str,
        region: str,
        repository: str,
    ) -> GCPResult[ArtifactRepositoryRef | None]:
        result = self._executor.run_json(
            [
                "artifacts",
                "repositories",
                "describe",
                repository,
                f"--location={region}",
                f"--project={project_id}",
                "--format=json",
            ]
        )
        if not result.ok:
            error = result.error
            if error is not None and error.code == "not_found":
                return GCPResult.success(None)
            return GCPResult.failure(error)  # type: ignore[arg-type]
        payload = result.value
        if not isinstance(payload, dict):
            return GCPResult.success(None)
        return GCPResult.success(_artifact_repo_from_payload(payload, project_id=project_id, region=region))

    def create_repository(
        self,
        *,
        project_id: str,
        region: str,
        repository: str,
        description: str,
    ) -> GCPResult[MutationOutcome[ArtifactRepositoryRef]]:
        existing = self.get_repository(project_id=project_id, region=region, repository=repository)
        if not existing.ok:
            return GCPResult.failure(existing.error)  # type: ignore[arg-type]
        if existing.value is not None:
            return GCPResult.success(MutationOutcome(action="existing", resource=existing.value))

        create_result = self._executor.run_text(
            [
                "artifacts",
                "repositories",
                "create",
                repository,
                "--repository-format=docker",
                f"--location={region}",
                f"--project={project_id}",
                f"--description={description}",
            ]
        )
        if not create_result.ok:
            return GCPResult.failure(create_result.error)  # type: ignore[arg-type]

        described = self.get_repository(project_id=project_id, region=region, repository=repository)
        if not described.ok:
            return GCPResult.failure(described.error)  # type: ignore[arg-type]
        resource = described.value or ArtifactRepositoryRef(
            project_id=project_id,
            region=region,
            repository=repository,
            format="DOCKER",
        )
        return GCPResult.success(MutationOutcome(action="created", resource=resource))


def build_image_uri(
    *,
    project_id: str,
    region: str,
    repository: str,
    image_name: str,
    tag: str,
) -> str:
    return f"{region}-docker.pkg.dev/{project_id}/{repository}/{image_name}:{tag}"


def _artifact_repo_from_payload(
    payload: dict[str, object],
    *,
    project_id: str,
    region: str,
) -> ArtifactRepositoryRef:
    format_name = str(payload.get("format", "DOCKER")).strip() or "DOCKER"
    name = str(payload.get("name", "")).strip()
    repository = name.rsplit("/", 1)[-1] if name else ""
    return ArtifactRepositoryRef(
        project_id=project_id,
        region=region,
        repository=repository,
        format=format_name,
    )
