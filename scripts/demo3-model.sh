#!/usr/bin/env bash
# TERMINAL 3 -- the deep-learning half: FRNet scored on real SemanticKITTI.
#
# Pretrained FRNet through our standalone port, per point against the .label
# ground truth. 200 frames of seq 08, the official validation sequence.
# --fast-scatter swaps the frustum reductions for torch.scatter_reduce and
# verifies equivalence before patching: ~35 min becomes ~1 min. JP's port is
# not edited. Both reduction paths agree at 90.3 % / 65.2 %.
#
# THE NUMBER IS 65.2 % mIoU, NOT THE 69.8 % ON THE SLIDES. Same 200 frames,
# same 15 per-class IoUs summing to 977.7: over 19 classes that is 51.5 % (the
# old union>0 bug), over the 15 classes actually present it is 65.2 %, over 14
# it is 69.84 -- which is what reached the handover. The missing fifteenth is
# other-ground: 150 gt points, IoU 0.0 %, present and therefore counted.
#
# Say first, before you are asked: this model is reported ALONGSIDE the map and
# never swapped into it. The pipeline's semantics come from the .label files, so
# no mapping number depends on segmentation quality. That is the point.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# The loader wants the directory holding poses/ and sequences/. In this clone
# that is data/dataset, NOT data. Without this the eval prints "no labelled
# frames found" and exits 1 -- it does not say the data root is wrong. Resolved
# here exactly as scripts/demo.sh does it, and never typed by hand.
if [[ -z "${VRGRID_DATA_ROOT:-}" ]]; then
  if   [[ -d "$REPO/data/dataset/poses" ]]; then export VRGRID_DATA_ROOT="$REPO/data/dataset"
  elif [[ -d "$REPO/data/poses"         ]]; then export VRGRID_DATA_ROOT="$REPO/data"
  fi
fi

SEQ="${1:-08}"
FRAMES="${2:-200}"

[[ -d "${VRGRID_DATA_ROOT:-}/sequences/$SEQ/labels" ]] || {
  printf '\033[31mno labels under %s/sequences/%s -- check VRGRID_DATA_ROOT\033[0m\n' \
    "${VRGRID_DATA_ROOT:-UNSET}" "$SEQ" >&2; exit 1; }

printf '\033[36m== terminal 3 -- FRNet on seq %s, %s frames (~1 min on the GPU) ==\033[0m\n' "$SEQ" "$FRAMES"
printf 'data root  %s\n' "$VRGRID_DATA_ROOT"
exec .venv/bin/python scripts/frnet_eval.py --seq "$SEQ" --frames "$FRAMES" --fast-scatter
