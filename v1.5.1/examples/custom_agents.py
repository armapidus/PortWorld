from __future__ import annotations

from typing import Any


AGENTS: list[dict[str, Any]] = [
    {
        "id": "mycompany.retail-coach",
        "name": "Retail Coach",
        "description": "In-store assistant tuned for product education and upsell prompts.",
        "system_prompt": (
            "You are a retail coaching assistant."
            " Keep answers short, prioritize conversion opportunities, and ask one clarifying question when needed."
        ),
        "tools": ["detect_intent"],
        "skills": ["intent_skill"],
        "metadata": {
            "main_llm_driver": "openai_compat",
            "main_llm_temperature": 0.3,
        },
    }
]

