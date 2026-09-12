#!/usr/bin/env bash
# TERMINAL 2 -- ghost removal off and on, as two windows side by side.
#
# Same 60 frames of seq 00, same schedule. The ONLY difference between the two
# windows is whether the visibility cleanup of math sec 10.4 runs.
#
# --new is load-bearing. Without it the second rerun finds the first one
# listening on port 9876, decides a viewer is already running, and streams its
# recording INTO that window -- you get one viewer holding both recordings
# instead of two windows to put side by side. --new always starts its own.
#
# Plays the baked .rrd files directly rather than through demo.sh: the
# demo.sh ghosts-off path is the --show-ghosts path, which prints
# "0 occupied cells, 0 cleared, 0 protected" -- a counter artifact (the
# occupied counter is only filled inside the ghost-removal branch). Harmless,
# but not something to explain on stage. This prints nothing.
#
# Numbers to quote:
#   13.5 % of the trail removed, 4.96 M cells cleared        (seq 08)
#   429,012 cells spared by the current-return guard         (seq 00, 60 frames)
# The guard number is the evidence the cleanup is conservative, not aggressive.
#
# Ctrl-C in this terminal closes both windows.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

RERUN="$REPO/.venv/bin/rerun"
[[ -x "$RERUN" ]] || RERUN="$(command -v rerun)" || {
  printf '\033[31mno rerun viewer found -- pip install rerun-sdk\033[0m\n' >&2; exit 1; }

for f in demo/ghosts-off.rrd demo/ghosts-on.rrd; do
  [[ -f "$f" ]] || { printf '\033[31mmissing %s -- run ./scripts/demo.sh bake\033[0m\n' "$f" >&2; exit 1; }
done

export RUST_LOG="${RUST_LOG:-error}"   # keep rerun's INFO banner off the projector
printf '\033[36m== terminal 2 -- ghosts OFF and ghosts ON, seq 00, 60 frames ==\033[0m\n'

"$RERUN" --new --server-memory-limit=8GiB demo/ghosts-off.rrd & OFF=$!
sleep 2                                # let the first one claim its port before the second looks
"$RERUN" --new --server-memory-limit=8GiB demo/ghosts-on.rrd  & ON=$!
trap 'kill "$OFF" "$ON" 2>/dev/null || true' INT TERM EXIT
printf 'two viewers up (pids %s, %s) -- drag them side by side. Ctrl-C here closes both.\n' "$OFF" "$ON"
wait
