#!/bin/bash
# Keep the test verdict authoritative and publish runner resource diagnostics
# while the suite is running: a runner shutdown cannot upload post-step logs.
set -euo pipefail

SHARD="${1:?usage: run-suite-shard.sh <shard> <shard-count>}"
SHARDS="${2:?usage: run-suite-shard.sh <shard> <shard-count>}"
if ! [[ "$SHARD" =~ ^[0-9]+$ && "$SHARDS" =~ ^[1-9][0-9]*$ ]] ||
   (( SHARD >= SHARDS )); then
  echo "invalid Android shard $SHARD/$SHARDS" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

resource_snapshot() {
  echo "Android shard $SHARD/$SHARDS resources at $(date -u +%FT%TZ)"
  free -m || true
  df -h . "${ANDROID_AVD_HOME:-${HOME}/.android/avd}" 2>/dev/null || true
  ps -eo pid,comm,rss --sort=-rss | head -n 12 || true
  for metric in /proc/pressure/memory /sys/fs/cgroup/memory.events; do
    if [ -r "$metric" ]; then
      echo "$metric"
      cat "$metric" || true
    fi
  done
  timeout 5 adb shell 'cat /proc/meminfo; df -h /data' 2>/dev/null || true
}

report_resources() {
  resource_snapshot | tee -a shard-resources.log
}

MONITOR_PID=""
cleanup() {
  if [ -n "$MONITOR_PID" ]; then
    # Stop both the loop and its pending sleep/adb query.
    pkill -P "$MONITOR_PID" 2>/dev/null || true
    kill "$MONITOR_PID" 2>/dev/null || true
    wait "$MONITOR_PID" 2>/dev/null || true
  fi
  report_resources
}
trap cleanup EXIT

report_resources
( while sleep 60; do report_resources; done ) &
MONITOR_PID=$!

# pipefail preserves test.py's failure; metrics and tee cannot turn a failed
# test into a successful job. Each deterministic shard runs once, no retries.
./tools/test.py -j 1 --flaky-tests=skip --timeout=300 --arch android \
  "--run=$SHARD,$SHARDS" parallel sequential 2>&1 | tee shard.log
