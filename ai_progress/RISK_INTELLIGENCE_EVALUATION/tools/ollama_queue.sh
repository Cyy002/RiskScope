#!/usr/bin/env bash
# THE single mutual-exclusion gate for every model batch (claude-b owns it).
#   tools/ollama_queue.sh [-t TASK_TIMEOUT_S] [-w MAX_WAIT_S] <label> <command...>      run a command under the lock
#   tools/ollama_queue.sh --hold-pid <PID> <label>                                       hold the lock until an already-running job (PID) exits
# Properties: atomic mkdir lock; stale-owner (dead pid) reclaim; bounded wait (default 3h -> exit 124); per-task timeout (default 2h -> exit 124);
# every event appended to /tmp/rs_queue.log. Never waits on process names (no pgrep self-matching), so no circular waits are possible:
# a waiter only ever waits on the lock, and the lock holder never waits on anything but its own command.
LOCK=/tmp/rs_ollama.lockdir; LOG=/tmp/rs_queue.log; TT=7200; MW=10800; HOLD=
while [ $# -gt 0 ]; do case "$1" in -t) TT=$2; shift 2;; -w) MW=$2; shift 2;; --hold-pid) HOLD=$2; shift 2;; *) break;; esac; done
LABEL=$1; shift; log() { echo "$(date +%H:%M:%S) [$LABEL] $*" | tee -a "$LOG"; }
start=$(date +%s)
while ! mkdir "$LOCK" 2>/dev/null; do
  O=$(cut -d' ' -f1 "$LOCK/owner" 2>/dev/null)
  if [ -n "$O" ] && ! kill -0 "$O" 2>/dev/null; then log "reclaiming stale lock of dead pid $O"; rm -rf "$LOCK"; continue; fi
  [ $(( $(date +%s) - start )) -gt "$MW" ] && { log "gave up waiting (>${MW}s) for: $(cat "$LOCK/owner" 2>/dev/null)"; exit 124; }
  sleep 15
done
echo "$$ $LABEL $(date +%H:%M:%S)" > "$LOCK/owner"; trap 'rm -rf "$LOCK"' EXIT INT TERM
if [ -n "$HOLD" ]; then log "holding lock for pid $HOLD"; while kill -0 "$HOLD" 2>/dev/null; do sleep 10; done; log "pid $HOLD finished, lock released"; exit 0; fi
log "start (task timeout ${TT}s)"; "$@" & CP=$!
( sleep "$TT"; kill -0 $CP 2>/dev/null && { log "TASK TIMEOUT -> killing $CP"; kill $CP; } ) & WD=$!
wait $CP; RC=$?; kill $WD 2>/dev/null; log "end rc=$RC"; exit $RC
