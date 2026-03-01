# AGENTS.md

## Purpose

This file defines the minimum documentation context that coding agents must load before proposing architecture, writing code, or reviewing changes in this repository.

## Platform Scope (Mandatory)

- Primary platform: **iOS**
- Assume iOS-first decisions unless a task explicitly asks for Android.

## Always-Read Documentation Map

Agents should read these in order before implementation:

1. Product requirements: `docs/PRD.md`
2. Product context: `docs/CONTEXT.md`
3. Acceptance criteria: `docs/PRD_ACCEPTANCE.md`
4. Interface appendix: `docs/PRD_APPENDIX_INTERFACES.md`
5. Meta Wearables Data Transfer SDK docs: `docs/Wearables DAT SDK.md`

## Meta Wearables SDK Prompting Rules

When asking an LLM to code against Meta Wearables SDK, prompts must:

- Be specific about platform: explicitly state **iOS**.
- Name the exact SDK module in scope: `MWDATCore`, `MWDATCamera`, or `MWDATMockDevice`.
- Pair API reference with integration docs:
  - Use the `llms.txt` endpoint for API surface and signatures.
  - Also include integration overview and iOS lifecycle/integration guidance for architecture decisions.

## Implementation Policy for This Repo

- Do not generate SDK usage code without citing the relevant module and iOS integration constraints from docs.
- If required SDK details are missing from local context, stop and fetch/ask for the exact Wearables SDK doc link or endpoint before continuing.
- Keep changes aligned with PRD + CONTEXT + acceptance criteria; if they conflict, flag it explicitly.

## Output Expectations for Agents

For each non-trivial code change, include:

- Which docs were consulted (file paths / SDK guide names).
- Which MWDAT module was used and why.
- Any iOS lifecycle or integration assumptions made.
