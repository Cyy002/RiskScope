#!/usr/bin/env bash
# One-shot acceptance run for a REAL host (Linux/macOS). Produces deploy/evidence/<os>-<arch>-<ts>.md
# to attach as proof. Never prints tokens. Exit 0 only if build+up+smoke+demo+restart-test all FULL PASS.
set -uo pipefail
cd "$(dirname "$0")/.."
TS=$(date -u +%Y%m%dT%H%M%SZ); OS=$(uname -s); ARCH=$(uname -m)
OUT="deploy/evidence/${OS}-${ARCH}-${TS}.md"
run() { local name=$1; shift; echo "### $name" >>"$OUT"; echo '```' >>"$OUT"; "$@" 2>&1 | grep -v -i -E 'bearer|token[=:]' | tail -40 >>"$OUT"; local rc=${PIPESTATUS[0]}; echo '```' >>"$OUT"; echo "exit=$rc" >>"$OUT"; echo "$name -> exit $rc"; [ "$rc" = 0 ] || VERDICT=FAIL; }
VERDICT=PASS
{ echo "# RiskScope platform acceptance"; echo "- date(UTC): $TS"; echo "- host: $OS $ARCH $(uname -r)"; echo "- podman: $(podman --version 2>&1)"; echo "- podman info arch/rootless: $(podman info --format '{{.Host.Arch}} rootless={{.Host.Security.Rootless}} os={{.Host.OS}}' 2>&1)"
  echo "- model: ${OLLAMA_MODEL:-qwen3:8b}  url: ${OLLAMA_URL:-http://host.containers.internal:11434}"
  echo "- NOTE: results below are from THIS host only; virtualised/emulated hosts must say so here: ${RS_HOST_NOTE:-<fill in: native / VM / WSL2 / emulated>}"; } >"$OUT"
curl -s -m 5 "${OLLAMA_PROBE_URL:-http://127.0.0.1:11434}/api/tags" >/dev/null && echo "- ollama reachable from host: yes" >>"$OUT" || echo "- ollama reachable from host: NO (smoke/demo will not be FULL PASS)" >>"$OUT"
run build deploy/riskscope.sh build
run up deploy/riskscope.sh up
run smoke deploy/riskscope.sh smoke
run demo deploy/riskscope.sh demo
run restart-test deploy/riskscope.sh restart-test
echo; echo "## VERDICT: $VERDICT" | tee -a "$OUT"; echo "evidence file: $OUT"
[ "$VERDICT" = PASS ]
