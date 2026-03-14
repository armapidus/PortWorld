from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.cli_app.gcp.executor import GCloudExecutor
from backend.cli_app.gcp.types import GCPResult


@dataclass(frozen=True, slots=True)
class CloudBuildSubmission:
    build_id: str | None
    image_uri: str
    log_url: str | None = None


class CloudBuildAdapter:
    def __init__(self, executor: GCloudExecutor) -> None:
        self._executor = executor

    def submit_build(
        self,
        *,
        project_id: str,
        source_dir: Path,
        dockerfile_path: Path,
        image_uri: str,
    ) -> GCPResult[CloudBuildSubmission]:
        result = self._executor.run_json(
            [
                "builds",
                "submit",
                str(source_dir),
                f"--project={project_id}",
                f"--tag={image_uri}",
                f"--file={dockerfile_path}",
                "--format=json",
            ],
            cwd=source_dir,
            timeout_seconds=self._executor.long_timeout_seconds,
        )
        if not result.ok:
            return GCPResult.failure(result.error)  # type: ignore[arg-type]
        payload = result.value
        if not isinstance(payload, dict):
            return GCPResult.success(CloudBuildSubmission(build_id=None, image_uri=image_uri, log_url=None))
        return GCPResult.success(
            CloudBuildSubmission(
                build_id=str(payload.get("id", "")).strip() or None,
                image_uri=image_uri,
                log_url=str(payload.get("logUrl", "")).strip() or None,
            )
        )
