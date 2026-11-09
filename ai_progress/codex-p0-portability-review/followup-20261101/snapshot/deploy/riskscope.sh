#!/usr/bin/env bash
# Portable Podman driver (Linux / macOS). Usage: deploy/riskscope.sh {build|up|smoke|restart-test|creds|down|purge}
# Uses its OWN names (riskscope-portable*, port 8100) so it never touches any other deployment.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${RS_NAME:-riskscope-portable}; VOL=${RS_VOLUME:-riskscope_portable_data}; PORT=${RS_PORT:-8100}
IMAGE=${RS_IMAGE:-localhost/riskscope-portable:1.0}
# Refuse production names/port so this kit can never touch a live deployment.
case "$NAME|$VOL|$PORT" in riskscope\|*|*\|riskscope_runtime\|*|*\|8000) echo "refusing reserved production name/port"; exit 3;; esac
HPORT=$PORT; [ "${RS_HOST_NETWORK:-0}" = 1 ] && HPORT=${RS_CONTAINER_PORT:-8000}
export OLLAMA_URL=${OLLAMA_URL:-http://host.containers.internal:11434}
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen3:8b}; TIMEOUT=${OLLAMA_REPLY_TIMEOUT_SECONDS:-120}
case "${1:-}" in
 build) podman build -t "$IMAGE" -f Containerfile . ;;
 up) podman volume exists "$VOL" || podman volume create "$VOL" >/dev/null
     podman rm -f "$NAME" >/dev/null 2>&1 || true
     NETARGS=(-p 127.0.0.1:$PORT:8000 --add-host=host.containers.internal:host-gateway)
     # Linux alternative when Ollama only listens on 127.0.0.1: RS_HOST_NETWORK=1 OLLAMA_URL=http://127.0.0.1:11434
     [ "${RS_HOST_NETWORK:-0}" = 1 ] && NETARGS=(--network=host)  # NOTE: app then binds host port 8000; stop anything using it first
     podman run -d --name "$NAME" --restart=unless-stopped "${NETARGS[@]}" -v "$VOL:/app/runtime" \
       -e OLLAMA_URL="$OLLAMA_URL" -e OLLAMA_MODEL="$OLLAMA_MODEL" -e OLLAMA_REPLY_TIMEOUT_SECONDS="$TIMEOUT" "$IMAGE"
     for i in $(seq 1 30); do curl -fs "http://127.0.0.1:$HPORT/health" && echo && exit 0; sleep 2; done
     echo "health check failed"; podman logs "$NAME"; exit 1 ;;
 smoke) podman exec "$NAME" python scripts/portable_smoke.py ;;
 restart-test) podman exec "$NAME" python -c "import json;print(json.load(open('/app/runtime/demo_credentials.json'))['engineer'])" > /tmp/rs_tok_before
     podman restart "$NAME"; sleep 8
     podman exec "$NAME" python -c "import json;print(json.load(open('/app/runtime/demo_credentials.json'))['engineer'])" | cmp - /tmp/rs_tok_before && echo "PERSISTENCE OK: credentials/db survived restart"; rm -f /tmp/rs_tok_before
     podman exec "$NAME" python scripts/portable_smoke.py ;;
 creds) podman exec "$NAME" cat /app/runtime/demo_credentials.json ;;
 down) podman rm -f "$NAME" ;;
 purge) podman rm -f "$NAME" || true; podman volume rm "$VOL" ;;
 *) echo "usage: $0 {build|up|smoke|restart-test|creds|down|purge}"; exit 2 ;;
esac
