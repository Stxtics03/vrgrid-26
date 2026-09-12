#!/usr/bin/env bash
# TERMINAL 1 -- the main thing: the foveated variable-resolution map.
#
# Plays the baked seq-00 recording (0-160). Identical pipeline to the live run,
# written to a Rerun file so it opens instantly and scrubs. Real SemanticKITTI
# scans, real Patchwork++ ground, the real MapEngine -- not a video.
#
# --new is load-bearing. Without it rerun finds whatever viewer already holds
# port 9876 and STREAMS INTO THAT WINDOW instead of opening its own, so all the
# demo scenes pile into one viewer. --new always starts its own.
#
# What to point at while it plays:
#   - ring boundary circles, cell size stepping 5 -> 10 -> 20 -> 40 cm outward
#   - the red circle: the 3.74 m blind cone. Say it out loud -- unknown, NEVER free
#   - world/map/free and world/map/unknown are separate entities on purpose
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

RERUN="$REPO/.venv/bin/rerun"
[[ -x "$RERUN" ]] || RERUN="$(command -v rerun)" || {
  printf '\033[31mno rerun viewer found -- pip install rerun-sdk\033[0m\n' >&2; exit 1; }
[[ -f demo/foveation.rrd ]] || {
  printf '\033[31mmissing demo/foveation.rrd -- run ./scripts/demo.sh bake\033[0m\n' >&2; exit 1; }

printf '\033[36m== terminal 1 -- foveation (seq 00, frames 0-160) ==\033[0m\n'
export RUST_LOG="${RUST_LOG:-error}"   # keep rerun's INFO banner off the projector
exec "$RERUN" --new --server-memory-limit=8GiB demo/foveation.rrd
