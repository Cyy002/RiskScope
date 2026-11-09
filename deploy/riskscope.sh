#!/usr/bin/env bash
# Portable Podman driver (Linux / macOS). Usage: deploy/riskscope.sh {build|up|smoke|demo|restart-test|creds|down|purge}
# Only ever touches resources whose names match riskscope-portable* AND that carry the
# io.riskscope.portable=1 ownership label. Production (riskscope / riskscope_runtime / :8000 /
# riskscope-poc:*) is rejected.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${RS_NAME:-riskscope-portable}; VOL=${RS_VOLUME:-riskscope_portable_data}; PORT=${RS_PORT:-8100}
IMAGE=${RS_IMAGE:-localhost/riskscope-portable:1.0}
LABEL=io.riskscope.portable=1
die() { echo "REFUSED: $*" >&2; exit 3; }
[[ "$NAME" =~ ^riskscope-portable[a-z0-9_.-]*$ ]] || die "container name must match riskscope-portable*"
[[ "$VOL" =~ ^riskscope_portable[a-z0-9_.-]*$ ]] || die "volume name must match riskscope_portable*"
[[ "$IMAGE" =~ ^localhost/riskscope-portable:[A-Za-z0-9_.-]+$ ]] || die "image must be localhost/riskscope-portable:<tag> (production riskscope-poc:* is protected)"
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] && [ "$PORT" != 8000 ] || die "port must be 1024-65535 and not 8000"
# Host-network mode is unsupported: the app binds 0.0.0.0:8000 (production port) and cannot be remapped.
[ "${RS_HOST_NETWORK:-0}" = 0 ] || die "RS_HOST_NETWORK is not supported; set OLLAMA_HOST=0.0.0.0 for Ollama and use the default gateway URL"
export OLLAMA_URL=${OLLAMA_URL:-http://host.containers.internal:11434}
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen3:8b}; TIMEOUT=${OLLAMA_REPLY_TIMEOUT_SECONDS:-120}

owned() { # $1=container|volume $2=name : ok if absent OR labeled ours
  if [ "$1" = container ]; then podman container exists "$2" 2>/dev/null || return 0
    [ "$(podman container inspect "$2" --format '{{index .Config.Labels "io.riskscope.portable"}}')" = 1 ]
  else podman volume exists "$2" 2>/dev/null || return 0
    [ "$(podman volume inspect "$2" --format '{{index .Labels "io.riskscope.portable"}}')" = 1 ]; fi
}
require_owned() { owned container "$NAME" || die "container $NAME exists but is not owned by this kit"
                  owned volume "$VOL" || die "volume $VOL exists but is not owned by this kit"; }
snap() { podman exec "$NAME" python -c "
import hashlib,sqlite3
c=open('/app/runtime/demo_credentials.json','rb').read()
db=sqlite3.connect('/app/runtime/agent.sqlite3')
ids=','.join(sorted(r[0] for r in db.execute('select id from analyses')))
print(hashlib.sha256(c).hexdigest(), hashlib.sha256(ids.encode()).hexdigest(), len(ids.split(',')) if ids else 0)"; }

case "${1:-}" in
 build) case "${RS_PLATFORM:-$(uname -m)}" in x86_64|amd64|linux/amd64) PLAT=linux/amd64;; arm64|aarch64|linux/arm64) PLAT=linux/arm64;; *) PLAT=;; esac
        podman build ${PLAT:+--platform "$PLAT"} -t "$IMAGE" -f Containerfile . ;;
 up) require_owned
     podman volume exists "$VOL" || podman volume create --label "$LABEL" "$VOL" >/dev/null
     podman container exists "$NAME" && podman rm -f "$NAME" >/dev/null
     podman run -d --name "$NAME" --label "$LABEL" --restart=unless-stopped -p 127.0.0.1:$PORT:8000 \
       --add-host=host.containers.internal:host-gateway -v "$VOL:/app/runtime" \
       -e OLLAMA_URL="$OLLAMA_URL" -e OLLAMA_MODEL="$OLLAMA_MODEL" -e OLLAMA_REPLY_TIMEOUT_SECONDS="$TIMEOUT" "$IMAGE" >/dev/null
     for i in $(seq 1 30); do
       [ "$(podman container inspect "$NAME" --format '{{.State.Running}}')" = true ] && curl -fs "http://127.0.0.1:$PORT/health" && echo && exit 0; sleep 2; done
     echo "health check failed"; podman logs "$NAME"; exit 1 ;;
 demo) require_owned; podman exec "$NAME" python scripts/demo_scenarios.py ;;
 smoke) require_owned; podman exec "$NAME" python scripts/portable_smoke.py ;;
 restart-test) require_owned
     rc1=0; podman exec "$NAME" python scripts/portable_smoke.py || rc1=$?   # creates an analysis first; persistence is checked regardless
     before=$(snap)
     podman restart "$NAME" >/dev/null; sleep 8
     after=$(snap)
     [ "$before" = "$after" ] || { echo "PERSISTENCE FAIL: credentials hash / analysis records changed across restart"; exit 1; }
     echo "PERSISTENCE OK: credentials hash and $(echo "$after" | cut -d' ' -f3) saved analysis record(s) identical after restart"
     rc2=0; podman exec "$NAME" python scripts/portable_smoke.py || rc2=$?
     [ "$rc1" = 0 ] && [ "$rc2" = 0 ] || { echo "restart-test: persistence ok but smoke rc=$rc1/$rc2 (see RESULT lines)"; exit 1; } ;;
 creds) require_owned; echo "(secrets) ->" >&2; podman exec "$NAME" cat /app/runtime/demo_credentials.json ;;
 down) require_owned; podman container exists "$NAME" && podman rm -f "$NAME" ;;
 purge) require_owned
     podman container exists "$NAME" && podman rm -f "$NAME" >/dev/null
     podman volume exists "$VOL" && podman volume rm "$VOL" ;;
 *) echo "usage: $0 {build|up|smoke|demo|restart-test|creds|down|purge}"; exit 2 ;;
esac
