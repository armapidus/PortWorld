# Port:🌍 Open Framework (v1.5.1)

`Port:🌍` est un framework open source pour brancher une solution IA au monde réel (voix + vision) sur lunettes connectées.

Vision: *you own the expertise, Port brings glasses + runtime orchestration*.

## Executive Summary

- Framework multimodal open source (Voxtral, Mistral, NVIDIA Nemotron, ElevenLabs, Bedrock-compatible).
- Personnalisation agent explicite via presets (`agent.id`) et instructions runtime.
- Intégration lean: une config courte, stable, et orientée plugin.
- Outils/skills/MCP extensibles sans modifier le core.
- Driver LLM explicite (`openai_compat` ou `strands`) pour sortir du “tout en .env”.
- Relay vocal temps réel: `pipeline/tts-stream` diffuse les tokens LLM vers ElevenLabs en live.

## Lean Onboarding (3 steps)

1. Lancer l’API.
2. Choisir un agent preset.
3. Envoyer un `runtime_config` minimal avec vos clés + éventuels overrides.

Template lean:

```bash
curl -sS http://127.0.0.1:8082/v1/config/quickstart-template | jq
```

Catalogue d’agents:

```bash
curl -sS http://127.0.0.1:8082/v1/agents | jq
```

## API Endpoints

- `GET /healthz`
- `GET /v1/debug/endpoints`
- `GET /v1/agents`
- `GET /v1/config/quickstart-template`
- `GET /v1/config/runtime-template`
- `POST /v1/pipeline`
- `POST /v1/elevenlabs/stream`
- `POST /v1/pipeline/tts-stream` (live LLM token relay -> ElevenLabs audio stream)
- `POST /v1/debug/ios/simulate`
- `POST /v1/debug/vision/frame`

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r v1.5.1/requirements.txt
```

Optionnel:

```bash
pip install -r v1.5.1/requirements-optional.txt
```

## Environment

Copie:

```bash
cp v1.5.1/.env.example .env
```

Minimum utile:

- `MAIN_LLM_API_KEY`
- `VOXTRAL_API_KEY` (si STT)
- `NEMOTRON_BASE_URL` + `NEMOTRON_API_KEY` (si vidéo)
- `ELEVENLABS_API_KEY` (si TTS)

Le reste peut rester par défaut et être overridé ponctuellement via `runtime_config`.

## Runtime Config: Lean First

`runtime_config` est accepté:
- en champ texte JSON (`multipart/form-data`) pour `/v1/pipeline`, `/v1/pipeline/tts-stream`, `/v1/debug/*`
- en objet JSON pour `/v1/elevenlabs/stream`

Exemple minimal:

```json
{
  "agent": {
    "id": "porto.field-tech",
    "instructions": "You are a plumber copilot. Be practical and safe."
  },
  "api_keys": {
    "main_llm": "<your-main-key>",
    "voxtral": "<your-voxtral-key>",
    "nemotron": "<your-nemotron-key>",
    "elevenlabs": "<your-elevenlabs-key>"
  },
  "generation": {
    "model": "mistral-large-latest",
    "temperature": 0.2,
    "max_tokens": 700
  },
  "trace": {
    "enabled": true,
    "backends": ["console"]
  }
}
```

`/v1/pipeline/tts-stream` fonctionne en relay live:
- token LLM entrant (stream)
- audio ElevenLabs sortant (stream)
- mode annoncé via header `X-TTS-Relay-Mode: llm-token-live`

## Agent Personalization Model

Personnalisation par priorité:

1. `runtime_config.agent.instructions`
2. `runtime_config.prompts.main_system_prompt`
3. preset agent (`agent.id`)
4. fallback `.env` (`MAIN_LLM_SYSTEM_PROMPT`)

Tools/skills/mcp sont fusionnés:
- preset agent + runtime overrides.

## Strands Driver

`main_llm_driver` peut être défini:
- `.env`: `MAIN_LLM_DRIVER=openai_compat` (défaut)
- `runtime_config.metadata.main_llm_driver` (`openai_compat` ou `strands`)
- metadata agent preset

Comportement:
- `openai_compat`: appel HTTP compatible OpenAI-style.
- `strands`: tentative d’exécution via package `strands`; fallback automatique vers `openai_compat` si indisponible/incompatible.

## Plugins

### Tools / Skills

Via `runtime_config.metadata.tool_modules`, un module peut exposer:
- `TOOLS = {"tool_name": callable}`
- ou `register_tools() -> dict[str, callable]`

### Agent Presets

Via `runtime_config.metadata.agent_modules` (ou `runtime_config.agent.metadata.agent_modules`), un module peut exposer:
- `AGENTS = [dict, ...]` ou `AGENTS = {"id": dict, ...}`
- ou `register_agents() -> list|dict`

Exemple: `v1.5.1/examples/custom_agents.py`.

## Headers API Key (optional)

- `X-Voxtral-API-Key`
- `X-Nemotron-API-Key`
- `X-Main-LLM-API-Key`
- `X-Vision-API-Key`
- `X-ElevenLabs-API-Key`

Priorité: `runtime_config.api_keys` > headers > `.env`.
