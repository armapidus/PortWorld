# OpenClaw Gateway Bridge Runbook

This runbook provides the default execution path for connecting PortWorld to OpenClaw when they run on separate hosts/clouds.

Default target state:

1. OpenClaw gateway listens only on loopback or private bind.
2. OpenClaw token auth stays enabled.
3. Reverse proxy serves a stable HTTPS hostname.
4. Public ingress allows `80/443` only.
5. Raw OpenClaw port stays non-public.
6. `GET /v1/models` and `POST /v1/responses` both succeed through the HTTPS hostname.

## 1) OpenClaw host discovery

Run:

```bash
bash scripts/discover_openclaw_gateway.sh
```

If OpenClaw is managed under a different Unix account, pass the service user explicitly:

```bash
OPENCLAW_SERVICE_USER=<service-user> bash scripts/discover_openclaw_gateway.sh
```

Manual fallback:

```bash
systemctl --user status openclaw-gateway --no-pager
openclaw config get gateway.auth.mode
sudo ss -ltnp | rg -i 'openclaw|LISTEN'
```

Port verification:

```bash
TOKEN="$(openclaw config get gateway.auth.token | tail -n 1)"
for p in 18789 18791 18792; do
  echo "=== $p ==="
  curl -sS -o /tmp/oc.$p.out -w "HTTP %{http_code}\n" \
    -H "Authorization: Bearer $TOKEN" \
    "http://127.0.0.1:$p/v1/models"
  head -c 200 /tmp/oc.$p.out; echo; echo
done
```

Use the port that returns JSON + `HTTP 200` for `/v1/models`.

If `/v1/models` returns the control UI HTML or `POST /v1/responses` returns `404`, enable the OpenAI-compatible HTTP endpoints in `~/.openclaw/openclaw.json` for the OpenClaw service user:

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true },
        "responses": { "enabled": true }
      }
    }
  }
}
```

Then restart the OpenClaw gateway service and re-run the probes.

## 2) Default production path: stable HTTPS endpoint

Use this unless the user explicitly requires private-mesh or dev-only tunneling.

Pattern:

1. Keep OpenClaw API internal on host (`127.0.0.1:<API_PORT>` or private bind).
2. Terminate TLS at reverse proxy (Caddy/Nginx/Traefik/Envoy).
3. Proxy to OpenClaw API port.
4. Restrict ingress by firewall or proxy policy.
5. Verify both `/v1/models` and `/v1/responses` through the final HTTPS hostname.

### Caddy example (Linux host)

```bash
sudo apt-get update
sudo apt-get install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
openclaw.example.com {
  reverse_proxy 127.0.0.1:<API_PORT>
}
EOF
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Verify:

```bash
curl -i "https://openclaw.example.com/v1/models" \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -i -X POST "https://openclaw.example.com/v1/responses" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"model":"openclaw/default","input":"Return exactly the word pong."}'
```

## 3) Private mesh mode

Use only when both runtimes already have a working private network/overlay and the user explicitly wants no public HTTPS endpoint.

Set PortWorld:

```bash
OPENCLAW_BASE_URL=http://<private-host-or-tailnet-name>:<api-port>
OPENCLAW_AUTH_TOKEN=<token>
```

Still keep gateway auth enabled.

## 4) Development mode: SSH local forward

Use for local testing only.

From PortWorld host:

```bash
ssh -fN -o ExitOnForwardFailure=yes \
  -L <LOCAL_PORT>:127.0.0.1:<API_PORT> \
  <user>@<openclaw-host>
```

Set PortWorld:

```bash
OPENCLAW_BASE_URL=http://127.0.0.1:<LOCAL_PORT>
OPENCLAW_AUTH_TOKEN=<token>
```

## 5) PortWorld wiring

Use CLI init flags when available:

```bash
portworld init --with-openclaw \
  --openclaw-url "<OPENCLAW_BASE_URL>" \
  --openclaw-token "<OPENCLAW_AUTH_TOKEN>" \
  --openclaw-agent-id "openclaw/default"
```

Or write env keys directly:

```bash
OPENCLAW_ENABLED=true
REALTIME_TOOLING_ENABLED=true
OPENCLAW_BASE_URL=<scheme://host[:port]>
OPENCLAW_AUTH_TOKEN=<token>
OPENCLAW_AGENT_ID=openclaw/default
```

## 6) Validation sequence

1. From PortWorld runtime:

```bash
curl -i "$OPENCLAW_BASE_URL/v1/models" \
  -H "Authorization: Bearer $OPENCLAW_AUTH_TOKEN"
```

Expect JSON model data, not the OpenClaw control UI HTML.

2. Execution probe:

```bash
curl -i -X POST "$OPENCLAW_BASE_URL/v1/responses" \
  -H "Authorization: Bearer $OPENCLAW_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"model":"openclaw/default","input":"Return exactly the word pong."}'
```

Expect `HTTP 200` JSON with a completed response payload.

3. PortWorld checks:

```bash
portworld doctor --target local
```

4. Realtime delegation flow:

- call `delegate_to_openclaw`
- poll with `openclaw_task_status`
- optional cancel with `openclaw_task_cancel`

If any of these fail, keep iterating on the OpenClaw host or ingress until the final HTTPS endpoint behaves like an OpenAI-compatible API, not just a reachable webpage.

## 7) Trusted proxy mode caveat

`gateway.auth.mode=trusted-proxy` is valid only with an identity-aware reverse proxy and blocked direct gateway access.

Checklist:

1. Gateway not directly reachable from internet.
2. Only proxy-origin traffic can reach gateway.
3. Proxy injects verified identity headers.
4. Firewall and routing prevent header spoofing by untrusted clients.
