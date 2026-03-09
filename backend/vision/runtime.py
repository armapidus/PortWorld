from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.settings import Settings

SUPPORTED_VISION_MEMORY_PROVIDERS = frozenset({"mistral"})


@dataclass(frozen=True, slots=True)
class VisionMemoryRuntime:
    settings: Settings
    provider_name: str
    model_name: str
    started: bool = field(default=False, init=False, repr=False, compare=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "VisionMemoryRuntime":
        provider_name = settings.vision_memory_provider
        if provider_name not in SUPPORTED_VISION_MEMORY_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_VISION_MEMORY_PROVIDERS))
            raise ValueError(
                f"Unsupported VISION_MEMORY_PROVIDER={provider_name!r}. Supported values: {supported}"
            )

        if provider_name == "mistral":
            settings.require_mistral_api_key()

        return cls(
            settings=settings,
            provider_name=provider_name,
            model_name=settings.vision_memory_model,
        )

    async def startup(self) -> None:
        object.__setattr__(self, "started", True)

    async def shutdown(self) -> None:
        object.__setattr__(self, "started", False)

    @property
    def enabled(self) -> bool:
        return True
