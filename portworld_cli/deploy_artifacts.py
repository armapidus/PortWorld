from __future__ import annotations


IMAGE_NAME = "portworld-backend"
IMAGE_SOURCE_MODE_SOURCE_BUILD = "source_build"
IMAGE_SOURCE_MODE_PUBLISHED_RELEASE = "published_release"
PUBLISHED_ARTIFACT_REPOSITORY_SUFFIX = "-ghcr"
GHCR_REMOTE_DOCKER_REPO = "https://ghcr.io"


def derive_published_artifact_repository(base_repository: str) -> str:
    normalized = base_repository.strip()
    if not normalized:
        normalized = "portworld"
    return f"{normalized}{PUBLISHED_ARTIFACT_REPOSITORY_SUFFIX}"
