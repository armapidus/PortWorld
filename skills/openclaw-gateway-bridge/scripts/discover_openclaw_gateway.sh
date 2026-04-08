#!/usr/bin/env bash
set -euo pipefail

if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required" >&2
  exit 1
fi

have_ss=true
if ! command -v ss >/dev/null 2>&1; then
  have_ss=false
fi

have_openclaw=true
if ! command -v openclaw >/dev/null 2>&1; then
  have_openclaw=false
fi

service_user="${OPENCLAW_SERVICE_USER:-}"
service_home=""
if [[ -n "$service_user" ]]; then
  service_home="$(getent passwd "$service_user" 2>/dev/null | cut -d: -f6 || true)"
fi

if [[ -z "$service_user" ]]; then
  detected_user="$(ps -eo user=,comm= | awk '$2 ~ /openclaw-gateway/ {print $1; exit}')"
  if [[ -n "$detected_user" ]]; then
    service_user="$detected_user"
    service_home="$(getent passwd "$service_user" 2>/dev/null | cut -d: -f6 || true)"
  fi
fi

config_path=""
if [[ -n "$service_home" && -f "$service_home/.openclaw/openclaw.json" ]]; then
  config_path="$service_home/.openclaw/openclaw.json"
elif [[ -f "${HOME}/.openclaw/openclaw.json" ]]; then
  config_path="${HOME}/.openclaw/openclaw.json"
fi

echo "== OpenClaw Gateway Discovery =="
echo "host: $(hostname)"
echo

echo "-- installation --"
if [[ -n "$service_user" ]]; then
  echo "service user: $service_user"
else
  echo "service user: unknown"
fi
if [[ -n "$config_path" ]]; then
  echo "config path: $config_path"
else
  echo "config path: not found"
fi
echo

if [[ "$have_openclaw" == "true" ]]; then
  echo "-- auth mode --"
  if [[ -n "$service_user" ]]; then
    sudo -u "$service_user" openclaw config get gateway.auth.mode 2>/dev/null || true
  else
    openclaw config get gateway.auth.mode 2>/dev/null || true
  fi
  echo
  echo "-- gateway token present --"
  if [[ -n "$service_user" ]]; then
    token_value="$(sudo -u "$service_user" openclaw config get gateway.auth.token 2>/dev/null | tail -n 1 || true)"
  else
    token_value="$(openclaw config get gateway.auth.token 2>/dev/null | tail -n 1 || true)"
  fi
  if [[ -n "$token_value" && "$token_value" != "null" ]]; then
    echo "present: yes (redacted)"
  else
    echo "present: no"
  fi
  echo
else
  echo "warning: openclaw CLI not found on PATH; skipping config checks" >&2
fi

echo "-- service status (best effort) --"
if [[ -n "$service_user" ]]; then
  service_uid="$(id -u "$service_user" 2>/dev/null || true)"
  if [[ -n "$service_uid" ]]; then
    sudo -u "$service_user" XDG_RUNTIME_DIR="/run/user/$service_uid" systemctl --user status openclaw-gateway --no-pager >/tmp/openclaw-gateway-status.out 2>&1 || true
  else
    echo "warning: could not resolve uid for service user $service_user" >/tmp/openclaw-gateway-status.out
  fi
else
  systemctl --user status openclaw-gateway --no-pager >/tmp/openclaw-gateway-status.out 2>&1 || true
fi
head -n 20 /tmp/openclaw-gateway-status.out || true
echo

echo "-- listeners --"
if [[ "$have_ss" == "true" ]]; then
  ss -ltnp | grep -Ei 'LISTEN|openclaw' || true
else
  echo "warning: ss not found; skipping listener dump" >&2
fi
echo

token_candidate="${OPENCLAW_GATEWAY_TOKEN:-${OPENCLAW_AUTH_TOKEN:-}}"
if [[ -z "$token_candidate" && "$have_openclaw" == "true" ]]; then
  if [[ -n "$service_user" ]]; then
    token_candidate="$(sudo -u "$service_user" openclaw config get gateway.auth.token 2>/dev/null | tail -n 1 || true)"
  else
    token_candidate="$(openclaw config get gateway.auth.token 2>/dev/null | tail -n 1 || true)"
  fi
fi

if [[ -z "$token_candidate" || "$token_candidate" == "null" ]]; then
  echo "warning: no token found; set OPENCLAW_GATEWAY_TOKEN or OPENCLAW_AUTH_TOKEN to run authenticated probes" >&2
fi

ports="${OPENCLAW_PORT_CANDIDATES:-18789 18791 18792}"
echo "-- /v1/models probes --"
for p in $ports; do
  echo "=== $p ==="
  if [[ -n "$token_candidate" && "$token_candidate" != "null" ]]; then
    curl -sS -o /tmp/openclaw_probe_$p.out -w "HTTP %{http_code}\n" \
      -H "Authorization: Bearer $token_candidate" \
      "http://127.0.0.1:$p/v1/models" || true
  else
    curl -sS -o /tmp/openclaw_probe_$p.out -w "HTTP %{http_code}\n" \
      "http://127.0.0.1:$p/v1/models" || true
  fi
  head -c 220 /tmp/openclaw_probe_$p.out || true
  echo
  echo
done

echo "-- /v1/responses probe (best effort) --"
if [[ -n "$token_candidate" && "$token_candidate" != "null" ]]; then
  for p in $ports; do
    echo "=== $p ==="
    body_file="/tmp/openclaw_probe_responses_$p.out"
    headers_file="/tmp/openclaw_probe_responses_$p.headers"
    cat > /tmp/openclaw_probe_request.json <<'JSON'
{"model":"openclaw/default","input":"Return exactly the word pong.","metadata":{"source":"gateway-discovery"}}
JSON
    curl -sS -D "$headers_file" -o "$body_file" \
      -H "Authorization: Bearer $token_candidate" \
      -H "Content-Type: application/json" \
      -X POST \
      --data @/tmp/openclaw_probe_request.json \
      "http://127.0.0.1:$p/v1/responses" || true
    sed -n '1p' "$headers_file" 2>/dev/null || true
    head -c 220 "$body_file" 2>/dev/null || true
    echo
    echo
  done
else
  echo "warning: skipping /v1/responses probe because no token is available" >&2
fi

echo "done."
