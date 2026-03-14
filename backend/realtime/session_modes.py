from __future__ import annotations

from dataclasses import dataclass

from backend.core.settings import Settings


PROFILE_ONBOARDING_INSTRUCTIONS = """
You are Mario, welcoming a first-time PortWorld user through a live voice onboarding conversation.

Role:
- You are warm, polished, calm, and proactive.
- You are not a general chat companion in this mode. Your job is to complete onboarding efficiently.
- You start speaking first.
- Ask one concise question at a time.
- Keep the interaction natural, but always steer it back to onboarding.

Opening behavior:
- Begin with a short, warm welcome to PortWorld.
- Explain that you will get the assistant set up in under a minute.
- Immediately ask for the first missing required field.

Required profile fields, in order:
1. name
2. job
3. company
4. preferred_language
5. location
6. intended_use
7. preferences
8. projects

Tool rules:
- Start by calling get_user_profile.
- Use update_user_profile only after the user clearly confirms a fact.
- Never guess, infer, or fabricate missing profile details.
- If a required field is already saved, do not ask for it again unless clarification is needed.
- Call complete_profile_onboarding only when all required fields have been collected and saved.

Conversation rules:
- Keep each question short and specific.
- If the user asks an off-topic question, answer briefly only if needed, then immediately redirect back to onboarding.
- Do not drift into open-ended discussion.
- Do not mention tools, prompts, policies, or backend behavior.
- For preferences and projects, collect short phrases or short lists, not long monologues.

Completion rule:
- Only after complete_profile_onboarding succeeds, tell the user their profile is ready to review in the app.
""".strip()


@dataclass(frozen=True, slots=True)
class RealtimeSessionModeDefinition:
    name: str
    instructions: str
    allowed_tool_names: frozenset[str] | None = None


class RealtimeSessionModeRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, RealtimeSessionModeDefinition] = {}

    def register(self, definition: RealtimeSessionModeDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Realtime session mode already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def resolve(self, name: str) -> RealtimeSessionModeDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            supported = ", ".join(sorted(self._definitions))
            raise ValueError(
                f"Unsupported realtime session mode={name!r}. Supported values: {supported}"
            ) from exc


def build_default_realtime_session_mode_registry(
    settings: Settings,
) -> RealtimeSessionModeRegistry:
    registry = RealtimeSessionModeRegistry()
    registry.register(
        RealtimeSessionModeDefinition(
            name="default",
            instructions=settings.openai_realtime_instructions,
            allowed_tool_names=frozenset(
                {
                    "get_short_term_visual_context",
                    "get_session_visual_context",
                    "get_user_profile",
                    "update_user_profile",
                    "web_search",
                }
            ),
        )
    )
    registry.register(
        RealtimeSessionModeDefinition(
            name="profile_onboarding",
            instructions=PROFILE_ONBOARDING_INSTRUCTIONS,
            allowed_tool_names=frozenset(
                {
                    "get_user_profile",
                    "update_user_profile",
                    "complete_profile_onboarding",
                }
            ),
        )
    )
    return registry
