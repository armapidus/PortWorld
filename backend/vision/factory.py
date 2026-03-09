from __future__ import annotations

from backend.core.settings import Settings
from backend.vision.contracts import VisionAnalyzer

SUPPORTED_VISION_MEMORY_PROVIDERS = frozenset({"mistral"})


def build_vision_analyzer(*, settings: Settings) -> VisionAnalyzer:
    provider_name = settings.vision_memory_provider
    if provider_name not in SUPPORTED_VISION_MEMORY_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_VISION_MEMORY_PROVIDERS))
        raise ValueError(
            f"Unsupported VISION_MEMORY_PROVIDER={provider_name!r}. Supported values: {supported}"
        )

    if provider_name == "mistral":
        from backend.vision.providers.mistral import MistralVisionAnalyzer

        return MistralVisionAnalyzer(
            api_key=settings.require_mistral_api_key(),
            model_name=settings.vision_memory_model,
            base_url=settings.mistral_base_url,
        )

    raise RuntimeError(f"Unsupported vision-memory provider: {provider_name}")
