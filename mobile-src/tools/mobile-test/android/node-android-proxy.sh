#!/bin/bash
# $TARGET is deliberately unquoted throughout: it expands to nothing, or to the
# two words `-s <id>` that adb wants.
# shellcheck disable=SC2086
set -e

# Use the environment variable to target a specific device
if [ "$DEVICE_ID" = "" ]; then
  TARGET=""
else
  TARGET="-s $DEVICE_ID"
fi

# Seconds to wait for a test to report a RESULT before treating it as failed,
# so a hung test can't block the whole run.
TIMEOUT="${NODE_ANDROID_PROXY_TIMEOUT:-120}"
START_TIMEOUT="${NODE_ANDROID_START_TIMEOUT:-10}"
LAUNCH_ATTEMPTS="${NODE_ANDROID_LAUNCH_ATTEMPTS:-3}"

# Bound individual transport calls too: a blocked ADB launch must not consume
# the upstream runner's entire per-test timeout before verdict polling starts.
adb_call() { timeout "${NODE_ANDROID_ADB_TIMEOUT:-15}" adb $TARGET "$@"; }

emit_output() {
  adb_call shell 'logcat -d -b main -v raw -s TestNode:E -s TestNode:I -s nodejs' \
    | sed '/^--------- beginning of/d'
}

# A failed ADB query is unknown, never proof that the app is stopped or that
# JS has not started. pidof is provided by the Android images used by the suite.
app_state() {
  adb_call shell 'pids=$(pidof nodejsmobile.test.testnode); rc=$?; if [ "$rc" = 0 ] && [ -n "$pids" ]; then echo RUNNING; elif [ "$rc" = 1 ]; then echo STOPPED; else exit 2; fi' \
    2>/dev/null | tr -d '\r\n'
}

TEST_PATH="$( cd "$( dirname "$0" )" && cd .. && cd .. && cd test && pwd )"

# Quoted: unquoted $* word-splits and glob-expands the test's own arguments
# (a `*` in a --test-name-pattern would be expanded against the cwd).
ARGS="$*"

# Per-launch token: the RESULT marker is tagged with it, so a marker emitted by
# an aborting test or a spawned grandchild can't be mis-attributed to a
# neighbouring test (the contiguous false-FAIL block seen on CI). [a-f0-9] only,
# so it's safe unquoted inside the am extra and in a grep/sed regex.
RUN_TOKEN="$(LC_ALL=C tr -dc 'a-f0-9' </dev/urandom 2>/dev/null | head -c 16)"
[ -n "$RUN_TOKEN" ] || RUN_TOKEN="${RANDOM}${RANDOM}$$"

# MainActivity creates this file BEFORE starting the Node thread. Its absence
# can authorize another launch only after a confirmed force-stop and a
# successful sandbox query. A lost ADB response cannot authorize a test retry.
started_state() {
  adb_call shell "run-as nodejsmobile.test.testnode sh -c 'if [ -f files/started-${RUN_TOKEN}.txt ]; then echo STARTED; else echo NOT_STARTED; fi'" \
    2>/dev/null | tr -d '\r\n'
}

ADB_START_COMMAND='am start -W -n nodejsmobile.test.testnode/nodejsmobile.test.testnode.MainActivity -e "nodeargs" "'$ARGS'" -e "substitutedir" "'$TEST_PATH'" -e "runtoken" "'$RUN_TOKEN'" '
started=""
for ((attempt=1; attempt<=LAUNCH_ATTEMPTS; attempt++)); do
  # Never ignore a failed force-stop or log clear: that previously allowed a
  # stale activity/output to stand in for a new test and burn the verdict wait.
  if ! preparation=$(adb_call shell "am force-stop nodejsmobile.test.testnode && run-as nodejsmobile.test.testnode sh -c 'rm -f files/result-*.txt files/started-*.txt'" 2>&1) ||
     [ "$(app_state || true)" != STOPPED ] ||
     ! preparation=$(adb_call logcat -c 2>&1); then
    echo "::warning::node-android-proxy: preparation failed (attempt $attempt/$LAUNCH_ATTEMPTS) for: $ARGS" >&2
    echo "$preparation" >&2
    sleep 0.1
    continue
  fi

  # Preserve the actual launch diagnostics, including stdout from am. ADB can
  # lose its reply after the app has started; the token, rather than the command
  # exit status, decides whether this test has begun.
  if ! launch_output=$(adb_call shell "$ADB_START_COMMAND" 2>&1); then
    echo "::warning::node-android-proxy: am start failed (attempt $attempt/$LAUNCH_ATTEMPTS) for: $ARGS" >&2
    echo "$launch_output" >&2
  fi
  start_deadline=$((SECONDS + START_TIMEOUT))
  while (( SECONDS < start_deadline )); do
    if [ "$(started_state || true)" = STARTED ]; then
      started=1
      break
    fi
    sleep 0.1
  done
  [ -z "$started" ] || break

  echo "::warning::node-android-proxy: no startup acknowledgement (attempt $attempt/$LAUNCH_ATTEMPTS) for: $ARGS" >&2
  echo "$launch_output" >&2
  adb_call shell 'logcat -d -b main -v brief -s AndroidRuntime:E -s ActivityManager:W' >&2 || true
  # Stop first to close the race with an app creating its marker after our last
  # poll. If it ever acknowledged this launch, JS may have run: fail, no retry.
  if ! adb_call shell 'am force-stop nodejsmobile.test.testnode' >&2 ||
     [ "$(app_state || true)" != STOPPED ] ||
     [ "$(started_state || true)" != NOT_STARTED ]; then
    echo "::error::node-android-proxy: cannot confirm test never started; refusing relaunch for: $ARGS" >&2
    emit_output || true
    exit 1
  fi
done
if [ -z "$started" ]; then
  echo "::error::node-android-proxy: app did not start test after $LAUNCH_ATTEMPTS attempts for: $ARGS" >&2
  emit_output || true
  exit 1
fi

# Is the app process still up? Empty `pidof` output = gone. The app never exits
# on its own (MainActivity stays after the node thread returns), so "gone"
# means the process died: a native crash, an abort, or a system kill.
app_alive() {
  [ "$(app_state || true)" != STOPPED ]
}

# The app writes the test's real exit code to a per-launch file in its sandbox
# (filesDir/result-<token>.txt). Read it via run-as — a durable, private channel
# immune to logcat's rate-limit / ring-buffer eviction / 4KB truncation that made
# a single scraped marker an unrecoverable false FAIL. PASS / FAIL / no-file
# (timeout) are now distinguishable.
RESULT_REL="files/result-${RUN_TOKEN}.txt"
RESULT=1
verdict=""
# Poll for the verdict, but watch the process too. A native crash (SIGSEGV /
# SIGKILL) never reaches the atexit fallback, so no verdict file is ever
# written and there is nothing left to wait for; without the liveness check a
# crash burns the full TIMEOUT and is then indistinguishable from a hang. The
# verdict direction is FAIL either way — this buys wall-clock and a triage
# signal, never a score.
#
# The verdict poll runs at 10 Hz: the median test finishes in ~100 ms, so a
# 1-second tick would dominate the per-test cost across a full-suite run. The
# liveness probe stays at ~1 Hz — it is a second adb round trip and only buys
# triage detail (crash vs hang).
POLL_HZ=10
waited=0
ticks=0
gone=""
while :; do
  verdict=$(adb_call shell "run-as nodejsmobile.test.testnode cat ${RESULT_REL} 2>/dev/null" 2>/dev/null | tr -d '\r\n' || true)
  case "$verdict" in
    PASS) RESULT=0; break ;;
    FAIL) RESULT=1; break ;;
  esac
  # Re-read once after the process died — it may have written the verdict and
  # exited between the two probes — then stop.
  if [ -n "$gone" ]; then break; fi
  if [ $((ticks % POLL_HZ)) -eq 0 ] && ! app_alive; then
    gone=1
    continue
  fi
  if [ "$waited" -ge "$TIMEOUT" ]; then break; fi
  sleep 0.1
  ticks=$((ticks + 1))
  waited=$((ticks / POLL_HZ))
done
case "$verdict" in
  PASS|FAIL) ;;
  *)
    if [ -n "$gone" ]; then
      echo "::warning::node-android-proxy: crashed (process gone after ${waited}s, no verdict) for: $ARGS" >&2
    else
      echo "::warning::node-android-proxy: hung (no verdict after full ${TIMEOUT}s) for: $ARGS" >&2
    fi
    ;;
esac

# Echo the raw stdout/stderr for test.py's .out comparison. The verdict no longer
# rides this stream, so there is nothing to strip.
emit_output

exit $RESULT
