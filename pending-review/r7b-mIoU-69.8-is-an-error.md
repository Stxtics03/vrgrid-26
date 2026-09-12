# pending-review: `r7b-mIoU-69.8-is-an-error.diff`

**Files touched:** `src/perception/semantics.py`, `src/perception/CLAUDE.md`
**Applied?** **YES — applied 2026-09-12 in `f3a0337`** to `src/perception/semantics.py` and `src/perception/CLAUDE.md`, on explicit
approval. The four *other* files that carried 69.8% were corrected separately in `c632027`. Kept as the rationale record.
**This corrects work I did in local commit `9b40ff2`.**

## What happened

Last session you asked me to change the FRNet figures to **65.2% mIoU**. I
flagged that five files on `main` said **69.8%** and recommended stating both
with their denominators; you said keep the parenthetical, *"cutting it creates
a new contradiction the night we're trying to remove old ones."* That reasoning
was right. **The parenthetical I wrote was not.**

I wrote that 69.8% is what you get *"if `other-ground` is excluded too"* —
framing it as a legitimate alternative denominator.

`docs/research-log.md:430` (Shrestha, 3 Sep — already on `main`) shows it is
**an arithmetic error**:

| divisor | value | what it is |
|---|---|---|
| 19 (all classes) | 51.46% | the withdrawn figure, from the `union > 0` bug |
| **15 (classes present)** | **65.18%** | what the committed script prints |
| 14 | 69.84% | the figure in the handover, the runbook and the slides |

The 15 per-class IoUs sum to **977.7**. 69.8% is that ÷ 14 — it drops
`other-ground`, which has **150 ground-truth points over the 200 frames and an
IoU of 0.0%**. Zero IoU is a *score*, not an absence: the class is present and
is therefore counted. Dropping it is not a defensible convention, it is a
miscount. Shrestha's own words: *"an arithmetic error in the recorded figure,
not a model, data or code difference."*

**Your original instruction — just use 65.2 — was simply correct**, and my
"state both denominators" advice was wrong on the facts, though right in
principle. This diff makes the two `src/perception/` files say so.

## What the diff changes

Both files stop presenting 69.8% as a variant and start naming it as an error,
with the divisor arithmetic and the source. Both keep the 98.3% single-frame
caveat, which is unaffected. **No code, no signatures, no behaviour** — the
`_PORT_BROKEN` string and the `get_frnet` docstring already say 65.2% and are
untouched.

## Why it is a decision and not an auto-apply

1. It edits `src/`, which tonight's rules put behind your review.
2. It **contradicts a framing you explicitly endorsed** last session. You chose
   "state both denominators" on the information available then; this is new
   information, and reversing it should be your call, not mine.
3. `research-log.md:430` names four *other* files still carrying 69.8% —
   `handover-2026-09-02.md:23` and `:169`, `demo-runbook.md:229`, and
   **`perception-dashboard-summary.md:150`, which is in JP's lane and which
   Shrestha explicitly left for you.** This diff does not touch them. Applying
   it alone leaves `src/perception/` correct and four docs wrong — you may
   prefer to do all five together.

## To apply

```bash
git apply pending-review/r7b-mIoU-69.8-is-an-error.diff
git diff --stat        # expect 2 files, docs/comments only
```
