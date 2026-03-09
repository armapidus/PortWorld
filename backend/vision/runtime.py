from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.settings import Settings
from backend.vision.contracts import VisionAnalyzer, VisionFrameContext, VisionObservation
from backend.vision.factory import build_vision_analyzer


@dataclass(frozen=True, slots=True)
class VisionMemoryRuntime:
    settings: Settings
    analyzer: VisionAnalyzer
    started: bool = field(default=False, init=False, repr=False, compare=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "VisionMemoryRuntime":
        return cls(settings=settings, analyzer=build_vision_analyzer(settings=settings))

    async def startup(self) -> None:
        await self.analyzer.startup()
        object.__setattr__(self, "started", True)

    async def shutdown(self) -> None:
        await self.analyzer.shutdown()
        object.__setattr__(self, "started", False)

    @property
    def enabled(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return self.analyzer.provider_name

    @property
    def model_name(self) -> str:
        return self.analyzer.model_name

    async def analyze_frame(
        self,
        *,
        image_bytes: bytes,
        frame_context: VisionFrameContext,
        image_media_type: str = "image/jpeg",
    ) -> VisionObservation:
        return await self.analyzer.analyze_frame(
            image_bytes=image_bytes,
            frame_context=frame_context,
            image_media_type=image_media_type,
        )
