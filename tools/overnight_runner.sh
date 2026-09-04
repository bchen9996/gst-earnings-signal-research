#!/usr/bin/env bash
# Overnight Claude Code runner for gst-earnings-signal-research.
#
# Alternates a PLAN pass and a BUILD pass, survives usage limits by sleeping
# and retrying, and stops cleanly on completion, a blocker, or a stop file.
#
#   ./tools/overnight_runner.sh [path-to-project]
#
# Requires: claude CLI, git, coreutils timeout. Reads TASK.md for the goal and
# CLAUDE_OVERNIGHT.md for the behavior contract.
#
# ---------------------------------------------------------------------------
# WHY THIS DIFFERS FROM THE ORIGINAL DRAFT
#
#   1. The plan pass does NOT use --permission-mode plan. Plan mode is
#      read-only, and in non-interactive -p mode there is nobody to approve an
#      exit from it, so a plan-mode pass can never write PLAN.md -- the very
#      file the whole loop uses as its memory. It gets a narrow write scope
#      instead.
#   2. CONTINUED is set in the PARENT shell. `x=$(f)` runs f in a subshell, so
#      an assignment inside the function is discarded and --continue would
#      never be passed.
#   3. Completion is matched on the last line, anchored and whole-line, so a
#      plan that merely mentions the sentinel cannot end the run.
#   4. Every claude call is wrapped in `timeout`, so a hung call cannot stall
#      the night.
#   5. A stale BLOCKED.md aborts immediately with an explanation instead of
#      silently ending the first loop.
#   6. Rate-limit handling backs off and caps retries rather than spinning.
#   7. The remote is verified before any pass runs. This repo pushes to the
#      user's own fork; a loop that can commit must not be pointed at someone
#      else's repository by accident.
# ---------------------------------------------------------------------------

set -uo pipefail

PROJECT_DIR="${1:-$(pwd)}"
cd "$PROJECT_DIR" || { echo "No such directory: $PROJECT_DIR"; exit 1; }

LOG_FILE="$PROJECT_DIR/overnight.log"
STOP_FILE="$PROJECT_DIR/STOP_OVERNIGHT"
PLAN_FILE="$PROJECT_DIR/PLAN.md"
BLOCKED_FILE="$PROJECT_DIR/BLOCKED.md"
CONTRACT="CLAUDE_OVERNIGHT.md"

EXPECTED_REMOTE="bchen9996/gst-earnings-signal-research"
CALL_TIMEOUT=3600           # hard cap on a single claude call (seconds)
RETRY_SLEEP=900             # first backoff after a usage limit (seconds)
RETRY_SLEEP_MAX=3600
MAX_RATE_RETRIES=12         # ~ up to 8h of waiting, then give up
CONTINUED=false
PASS=0

touch "$LOG_FILE"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# --- preflight -------------------------------------------------------------
preflight() {
  local remote
  remote="$(git remote get-url origin 2>/dev/null)" || {
    log "FATAL: not a git repository, or no 'origin' remote."; exit 1; }
  case "$remote" in
    *"$EXPECTED_REMOTE"*) : ;;
    *) log "FATAL: origin is '$remote', expected '$EXPECTED_REMOTE'."
       log "       Refusing to run an autonomous commit loop against an"
       log "       unexpected repository. Edit EXPECTED_REMOTE to override."
       exit 1 ;;
  esac

  [[ -f "$CONTRACT" ]] || { log "FATAL: missing $CONTRACT"; exit 1; }
  [[ -f "TASK.md"   ]] || { log "FATAL: missing TASK.md"; exit 1; }

  if [[ -f "$BLOCKED_FILE" ]]; then
    log "FATAL: $BLOCKED_FILE exists from an earlier run. Read it, resolve it,"
    log "       and delete it before starting a new night. Refusing to start."
    exit 1
  fi
  command -v timeout >/dev/null || { log "FATAL: 'timeout' not found"; exit 1; }
  log "preflight OK -- origin=$remote"
}

# --- one claude turn -------------------------------------------------------
# $1 = plan|build   $2 = prompt.  Echoes output; caller sets CONTINUED=true.
run_claude() {
  local kind="$1" prompt="$2" flags=()

  if [[ "$kind" == "plan" ]]; then
    # NOT --permission-mode plan: that is read-only and cannot write PLAN.md.
    # Narrow write scope instead -- research freely, but the only mutations
    # allowed are the two bookkeeping files.
    flags+=(--allowedTools "Read,Grep,Glob,Bash(git log:*),Bash(git status:*),Write,Edit")
  else
    # Unattended edits need this: there is no terminal to answer prompts.
    # The contract, not the permission system, is what keeps this bounded.
    flags+=(--dangerously-skip-permissions)
  fi

  [[ "$CONTINUED" == true ]] && flags+=(--continue)

  timeout --signal=INT "$CALL_TIMEOUT" claude -p "$prompt" "${flags[@]}" 2>&1
  local rc=$?
  if [[ $rc -eq 124 ]]; then
    echo "__RUNNER_TIMEOUT__ claude exceeded ${CALL_TIMEOUT}s"
  fi
  return $rc
}

is_rate_limited() {
  # Deliberately narrow. A broad grep matches Claude *discussing* usage limits
  # in its own prose and burns 15 minutes on a false positive.
  grep -qiE "(usage limit reached|you have hit your usage limit|rate[ _-]?limit(ed)? )" <<<"$1"
}

plan_says_complete() {
  [[ -f "$PLAN_FILE" ]] || return 1
  tail -n 1 "$PLAN_FILE" | tr -d '\r' | grep -qix "ALL STEPS COMPLETE"
}

# --- main loop -------------------------------------------------------------
preflight
log "=== Overnight run starting in $PROJECT_DIR ==="
rate_retries=0
sleep_for=$RETRY_SLEEP

do_pass() {                       # $1=kind  $2=prompt  -> 0 ok, 1 retry, 2 stop
  local kind="$1" prompt="$2" out
  log "--- ${kind} pass (#$((++PASS))) ---"
  out="$(run_claude "$kind" "$prompt")"
  printf '%s\n' "$out" >>"$LOG_FILE"

  if is_rate_limited "$out"; then
    if (( ++rate_retries > MAX_RATE_RETRIES )); then
      log "Usage limit persisted across $MAX_RATE_RETRIES retries. Stopping."
      return 2
    fi
    log "Usage limit hit (retry $rate_retries/$MAX_RATE_RETRIES). Sleeping ${sleep_for}s."
    sleep "$sleep_for"
    (( sleep_for = sleep_for * 2 > RETRY_SLEEP_MAX ? RETRY_SLEEP_MAX : sleep_for * 2 ))
    return 1
  fi

  rate_retries=0; sleep_for=$RETRY_SLEEP
  CONTINUED=true                  # parent shell -- this is the point
  grep -q "__RUNNER_TIMEOUT__" <<<"$out" && log "WARN: ${kind} pass timed out."
  [[ -f "$BLOCKED_FILE" ]] && { log "BLOCKED.md written. Stopping for review."; return 2; }
  return 0
}

while true; do
  [[ -f "$STOP_FILE" ]] && { log "Stop file found. Exiting."; break; }

  do_pass plan "Follow the planning-pass instructions in $CONTRACT now."
  case $? in 1) continue ;; 2) break ;; esac

  if plan_says_complete; then log "Plan reports work complete. Exiting."; break; fi

  do_pass build "Follow the build-pass instructions in $CONTRACT now."
  case $? in 1) continue ;; 2) break ;; esac

  sleep 5
done

log "=== Overnight run finished (passes: $PASS) ==="
