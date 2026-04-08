---
name: openclaw-gateway-bridge
description: Configure and harden remote OpenClaw gateway connectivity for PortWorld across cloud providers. Use when OpenClaw runs on a VM/VPS/ECS host different from PortWorld, and the user wants the agent to perform end-to-end setup (exposure method, auth, reverse proxy/tunnel, PortWorld env wiring, and validation) with minimal manual steps.
---

# OpenClaw Gateway Bridge

## Overview

Use this skill when OpenClaw and PortWorld run on different hosts/clouds and the user wants a working, secure integration without provider-specific assumptions.

Default production posture and expected end state:

1. Keep OpenClaw gateway bound to loopback or private bind.
2. Keep OpenClaw gateway auth enabled in `token` mode.
3. Expose a stable HTTPS endpoint in front of the gateway.
4. Keep direct public access to the raw OpenClaw port blocked.
5. Point PortWorld at the HTTPS root using `OPENCLAW_BASE_URL` and `OPENCLAW_AUTH_TOKEN`.

Do not expose unauthenticated raw gateway ports to the public internet.

## Use This Flow

Unless the user explicitly requires a private mesh or dev-only tunnel, always implement `prod-https`.

1. Discover OpenClaw gateway status, auth mode, API port, and service user on the OpenClaw host.
   Check whether OpenClaw runs under the current user or a different service user.
2. Ensure the gateway is locally reachable on the OpenClaw host with bearer auth.
   If `/v1/models` returns HTML or `/v1/responses` returns `404`, enable the OpenAI-compatible HTTP endpoints before continuing.
3. Create a stable HTTPS ingress in front of the gateway.
   Use a reverse proxy on the same host whenever possible.
4. Open only `80/443` publicly and keep the raw gateway port unexposed.
5. Wire PortWorld env (`OPENCLAW_*`) to the HTTPS root and run `portworld doctor`.
6. Prove end-to-end with `/v1/models`, `/v1/responses`, and delegated task lifecycle.

For detailed command recipes, use [references/runbook.md](references/runbook.md).

## Discovery Commands

On the OpenClaw host, run the bundled script first:

```bash
bash scripts/discover_openclaw_gateway.sh
```

If running remotely:

```bash
OPENCLAW_SERVICE_USER=<service-user> ssh <user>@<host> 'bash -s' < scripts/discover_openclaw_gateway.sh
```

This script reports:

- gateway service state
- likely OpenClaw service user and config path
- auth mode
- listeners and candidate API ports
- `/v1/models` probe results per port

## Connectivity Modes

Pick exactly one mode and explain why:

1. `prod-https`
   Use this by default. This is the correct mode for Cloud Run, ECS, Fargate, and most self-hosted PortWorld deployments.
2. `private-mesh`
   Use only when both PortWorld and OpenClaw already have a working private mesh route and the user explicitly wants no public HTTPS endpoint.
3. `dev-tunnel`
   Use only for local development or temporary operator sessions. Never leave this as the final production setup.

If the user asks for provider-agnostic setup and does not force an option, choose `prod-https` without asking.

## Agent Responsibilities

Do the setup on the user’s behalf whenever credentials and host access are available.

1. Detect the actual OpenClaw runtime shape instead of assuming defaults.
2. Modify the OpenClaw host as needed:
   - config file
   - service restart
   - reverse proxy
   - firewall or security group rules
   - DNS validation when applicable
3. Do not stop after “the proxy is installed”.
   Finish only when the HTTPS endpoint returns working OpenClaw API responses.
4. When cloud/provider-specific work is required, adapt the exact commands to that provider.
   The required end state matters more than the specific tool used to reach it.

## Required PortWorld Wiring

Always set these on the PortWorld runtime:

```bash
OPENCLAW_ENABLED=true
REALTIME_TOOLING_ENABLED=true
OPENCLAW_BASE_URL=<scheme://host[:port]>
OPENCLAW_AUTH_TOKEN=<gateway token>
OPENCLAW_AGENT_ID=openclaw/default
```

Notes:

- `OPENCLAW_BASE_URL` is the root URL only (no `/v1/...` suffix).
- PortWorld uses OpenClaw HTTP endpoints (`/v1/models`, `/v1/responses`). No WebSocket setup is required for PortWorld delegation.

## Validation Gates

Pass all gates before declaring setup complete:

1. OpenClaw-side probe:
   - `curl -i "$BASE_URL/v1/models" -H "Authorization: Bearer $TOKEN"` returns `200`.
   - response body is JSON model metadata, not the control UI HTML shell.
2. OpenClaw-side execution probe:
   - `curl -i -X POST "$BASE_URL/v1/responses" ...` returns `200` JSON, not `404`.
3. PortWorld-side doctor:
   - `portworld doctor --target local` (or target-specific doctor if applicable) shows OpenClaw checks passing.
4. Delegation flow:
   - `delegate_to_openclaw` returns `task_id`.
   - `openclaw_task_status` reaches terminal state (`succeeded|failed|cancelled`).

Do not declare success if only DNS or TLS is working while the OpenClaw API is still returning HTML, `404`, or auth failures.

## Security Guardrails

1. Never print or log full tokens in outputs.
2. Prefer private/allowlisted ingress over internet-wide exposure.
3. If using `trusted-proxy` auth mode, ensure direct gateway access is blocked and only proxy-origin traffic is accepted.
4. If non-loopback bind is enabled, verify firewall rules are tightened before finalizing.
