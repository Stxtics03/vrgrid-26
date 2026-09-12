# Morning summary — overnight 2026-09-11
### …plus a 2026-09-12 update, below. Read that first.

**Nothing was pushed. `origin` was never contacted. `vrgrid-26` was never
checked, created or mentioned to GitHub.** Four local commits, all additive.

**Read this first:** three of your eight tasks could not be started, because
they reference things that do not exist in this repository. Details in
[§ Needs your call](#needs-your-call). I did not guess at them.

---

## 1. What got done

| # | task | status | output |
|---|---|---|---|
| 1 | R9 per-stage latency + VRAM | **done, with a caveat** | `reports/r9-per-stage-latency-and-memory.md` |
| 2 | `--fast-scatter` re-verify | **done** | `reports/fast-scatter-reverification.md` |
| 3 | R7 hazard miss rate | **done** | `reports/r7-hazard-miss-rate.md` + `pending-review/r7-readme-wording.md` |
| 4 | R1 accuracy table | **done (one reading — see below)** | `reports/r1-accuracy-by-class-and-range-band.md` |
| 5 | R3 design doc | **NOT STARTED** — see Needs your call |
| 6 | R5 sticky-bit design doc | **NOT STARTED** — see Needs your call |
| 7 | CARLA groundwork | **NOT STARTED** — see Needs your call |
| 8 | log inconsistencies | **done** | § New inconsistencies, below |

### Commits (local only)

```
7eb0d2d reports: R1 accuracy by range band and class, and the 69.8% correction
2811ebc reports: R7 hazard miss rate, with the denominator stated
8239918 reports: R9 per-stage latency/memory, and --fast-scatter re-verification
9b40ff2 perception: correct the FRNet headline figures (yours, from last session)
```

### The three findings that matter most

**(a) The 10 Hz claim does not reproduce — under any configuration.**
> ⚠️ **SUPERSEDED 12 Sep — this conclusion is WITHDRAWN.** The measurements it
> rests on are not stable on this machine, and the real explanation is
> different and better. See the update section at the end of this file and
> `reports/latency-10hz-diagnosis.md`. Left in place as a record of what I
> thought overnight, not as a finding.

> **Resolved 2026-09-12.** That line has since been corrected in the handover
> (row, latency note, and a new *Not proven* entry for 10 Hz). Full
> reconstruction: `reports/latency-gap-investigation.md`. Kept below as written.

`handover-2026-09-02.md:20` listed, under *"measured on real data and holding"*,
frame p50 **80.78** / p99 **97.72**, "meets 10 Hz", from `timing_table.py --seq 08`.
Same script, same sequence, tonight:

| configuration | p50 | p99 | |
|---|---|---|---|
| cold cache, Patchwork++ | 152.27 | 187.68 | MISSES |
| warm cache, Patchwork++ | 106.74 | 132.22 | MISSES |
| warm cache, `--no-patchworkpp` | 87.95 | 106.20 | MISSES |

The cold/warm gap is entirely `load` (page cache); the Patchwork++ gap is
entirely `ground` (21.09 → 0.42 ms). So the logged figure is **consistent with
having been measured on the semantic-class fallback**, not the geometric
segmenter. I can't reproduce it exactly and can't rule out a quieter machine or
older code. Either way, **p99 exceeds 100 ms in everything I can run.**

**(b) Drivable-surface accuracy is flat with range, and much better than the
aggregate.** Pooling only the §7.1 drivable set:

| seq | ring 0 | ring 1 | ring 2 | (aggregate) |
|---|---|---|---|---|
| 07 | **0.95** | **1.14** | **1.20 cm** | 1.78 / 3.60 / 5.91 |
| 08 | **1.16** | **1.10** | **1.12 cm** | 1.17 / 2.31 / 4.89 |
| 00 | **2.22** | **3.13** | **3.68 cm** | 2.74 / 6.77 / 34.10 |

The per-ring aggregate grows with range because the *non-drivable fraction*
grows and is rougher — not because the ground estimate degrades. For a claim
about the planning surface, this is the stronger and more honest number.

**(c) The "unexplained" seq-00 ring-2 dispersion is vegetation.** 1,261 cells
(11% of the ring) at **100.77 cm RMSE with +37.85 cm signed bias**. Excluding
them takes the ring from 34.10 → **5.54 cm**. §2b currently calls this
unexplained and offers a hypothesis; it is now a finding.

---

## 2. In `pending-review/` — each needs a human decision

### `timing-table-unicode-crash.diff` (+ `.md`)
`scripts/timing_table.py --alloc` prints its table then **crashes** with
`UnicodeEncodeError` on the cp1252 console — exits **1** on a successful run, so
it can't be used from a Makefile or CI. Verified: as-is exit 1, patched exit 0.
**Why you decide:** it's Shrestha's file; the house style uses `⚑` deliberately;
and there's a competing one-line `sys.stdout.reconfigure(encoding="utf-8")` fix
that would cover *every* script instead of two call sites. Other scripts almost
certainly have the same latent crash — I only checked this one.

### `r7-readme-wording.md`
You asked for the R7 number but not the README edit. **Having computed it, my
advice is not to ship a percentage at all**: the denominators are 19, 3 and 38
cells, the three sequences disagree by 42 points, and every 95% interval
overlaps. Quoting *"0% miss rate on seq 08"* would be actively misleading — it's
0/3, interval to 56%. Three options with a recommendation; **no diff attached**,
because the recommendation is "not yet".

### `r7b-mIoU-69.8-is-an-error.diff` (+ `.md`)
**This corrects work I did in your commit `9b40ff2`.** Last session I argued for
keeping a parenthetical explaining 69.8% as an alternative denominator, and you
agreed. `research-log.md:430` — already on `main`, Shrestha, 3 Sep — shows
**69.8% is an arithmetic error**: the 15 per-class IoUs sum to 977.7, and 69.8%
is that ÷ **14**, dropping `other-ground`, which has 150 GT points and IoU 0.0%
and is therefore present and countable. 65.2% is 977.7 ÷ 15.
**Your original instruction — just use 65.2 — was simply right.**
**Why you decide:** it edits `src/`, and it reverses a framing you explicitly
endorsed. Also, four *other* files still carry 69.8% (`handover:23` and `:169`,
`demo-runbook:229`, `perception-dashboard-summary:150` — the last is in your
lane and Shrestha left it for you), so you may want all five done together.

---

## 3. Needs your call

### Tasks 5, 6, 7 reference things that aren't in this repo

I searched the whole tree for every topic before concluding this. **Zero hits**
for: `sticky`, `nearest.corner`, `hazard.miss`, `VRAM`, `block.cent`,
`boundary.snap`, `miss.rate`, and `carla` (case-insensitive, all file types,
excluding `__pycache__`).

- **Task 5 (R3 — "nearest-corner test instead of block-centre, boundary-snapping").**
  No such bug, discussion or code is referenced anywhere. Writing a detailed
  kernel-implementation handoff for Shrestha/Pratyushi from my own guess at what
  the bug is would be worse than writing nothing — it would look authoritative
  and could send them at a problem that doesn't exist. **Not attempted.**
- **Task 6 (R5 — "sticky bit: which byte, which classes, decay logic").** Same.
  The cell struct is 12 bytes and frozen; a proposal about which byte to use
  needs to start from the actual motivating defect, which I don't have.
- **Task 7 (CARLA groundwork — "continue building this").** There is no CARLA
  work in this repo or in any sibling folder to continue. Starting a simulator
  integration from zero, unsupervised, on a guess at the intended scope isn't
  something I should do.

The R-numbers in `docs/research-modules.md` are the **research tracks**
(R1 = prior art, R2 = dynamics/segmentation, R3 = traversability/evaluation,
owned by Shriniwas/Hriday/Prathyushree) — they don't match your descriptions.
**My guess is these came from a different session or a backlog doc that lives
outside the repo.** If you paste that list, tasks 5 and 6 are a couple of hours
each.

### Task 4 had two readings and I picked one

*"Per-class, per-range-band accuracy with n"* could mean **(a)** FRNet
segmentation IoU per class × distance band, or **(b)** mapping height accuracy
per class × ring. No "accuracy-table skeleton" exists to disambiguate, and
`metrics.py` has only `*_per_ring` functions.

**I chose (b)**, because you said *"using the existing eval harness"* and that
is `src/eval/`, not `frnet_eval.py`; and because rings *are* the range bands.
If you meant (a), say so — it's a different run and roughly an hour with
`--fast-scatter`.

### Not touched, as instructed

The **Patchwork++ singleton / determinism bug** — I did not investigate further
and did not go near it. It is still failing:
`tests/test_determinism.py::test_real_sequence_replay_is_identical`, and CI is
green only because the runner has no KITTI data and the test skips.

---

## 4. New inconsistencies found tonight (task 8 — logged, not fixed)

1. **`handover-2026-09-02.md:23` — the 10 Hz claim.** Does not reproduce; see
   §1(a). It sits in the *proven* table.
2. **`research-log.md:411` — the `--fast-scatter` speed-ups.** Logged as
   **1093×** / **3229×**; measured tonight at identical shapes over three runs
   (±3%) as **~144×** / **~64×**. The loop is ~9× faster tonight and the mean
   shim ~6× slower. The engineering conclusion is unchanged, but the **3.3 h**
   and **35 min** baselines in that entry are extrapolations from the slow loop
   and would be ~9× too large. The 3 Sep numbers record no torch version or
   thread count, so **they are not re-derivable from what the log says**.
3. **`known-limitations.md` §2b is stale post-PR #31.** #31 changed
   `_ring_cells` to filter on `ring_of(centre) == ring`, so the whole table
   moved: seq 07 ring 0 reads **1.78** today against the doc's **1.76**, ring 1
   3.48 → 3.60, ring 2 6.13 → 5.91, ring 3 16.34 → 16.93, and there's a new
   `cov` column. #31's own PR said the table needed regenerating before ρ is
   quoted to two decimals. **It hasn't been.**
4. **§2b's "unexplained" seq-00 ring-2 dispersion is explained** — vegetation,
   §1(c).
5. **69.8% mIoU is an arithmetic error**, still carried by four files —
   see `pending-review/r7b-…`.
6. **`plan_regret.restrict()` silently drops `trav`.** It builds `CostMap(...)`
   without it, so `restrict(x).trav is None` and `restrict(x).low_confidence()`
   degrades to `.unknown` alone — exactly the confound `baa44b4` fixed and that
   `trav` was added to expose. **Latent only:** `--confound` reads
   `low_confidence()` off *unrestricted* maps, so no live caller hits it. It
   will bite the next person who restricts first.
7. **`--alloc` is silently ignored with `--seq`.** `--seq` routes to
   `print_real_table(t)`, which takes no `alloc` argument. No warning. Latency
   on real data and per-stage memory therefore cannot come from one run.
8. **`pyramid` is timed on the synthetic path but absent from the real one.**
   Either `run_real` doesn't drive it or it isn't instrumented there.
9. **Pre-existing lint error on `main`:** `tests/test_metrics.py:472`
   `E741 Ambiguous variable name: 'l'` (from `014d388`). Present on
   `origin/main` too. CI is green because ruff 0.16.5 doesn't enable E741 while
   local 0.12.0 does — the ruff version pin (`ruff>=0.4`, unpinned) is still
   unaddressed.

---

## 5. Git status

```
branch           main
local HEAD       7eb0d2d
origin/main      5e0ebf3   (untouched — never fetched, never pushed)
ahead by         4 commits, all local
working tree     clean
```

- **Nothing pushed.** No `git push`, no `git fetch`, no network call to
  `origin` at any point tonight.
- **`vrgrid-26` never touched** — not checked for existence, no remote added.
- **No tracked file modified.** Everything committed is a new file under
  `reports/` or `pending-review/`. Proposed edits to tracked files are diffs in
  `pending-review/`, unapplied.
- **`src/perception/frnet/` untouched.**
- **Tests / lint:** `ruff check .` → 1 error, pre-existing on `origin/main`
  (item 9). Full suite result appended below.

### Full test suite (on this tree)

```
1 failed, 672 passed, 3 skipped in 122.14s
FAILED tests/test_determinism.py::test_real_sequence_replay_is_identical
```

**The one failure is the Patchwork++ determinism bug you told me not to touch**
(`replay() != replay()` — the cached `pypatchworkpp` estimator carries state
between runs). It is pre-existing, unrelated to anything done tonight, and
identical to the state I found it in. **Not investigated further, not fixed.**

Nothing I added can affect the suite: every commit tonight is a new `.md` or
`.diff` file under `reports/` or `pending-review/`.

---
---

# Update — 2026-09-12, after JP's review decisions

## Applied (committed `f3a0337`)

| diff | result |
|---|---|
| `timing-table-unicode-crash.diff` | applied. `--alloc` now exits **0** (was 1). Broader stdout-reconfigure question **deferred**, not answered. |
| `r7b-mIoU-69.8-is-an-error.diff` | applied to `src/perception/semantics.py` and `src/perception/CLAUDE.md`. |

`ruff`: 1 error, the pre-existing `tests/test_metrics.py:472` E741. Tests green.

### ✓ DONE 2026-09-12 (was: CONFIRMED FOLLOW-UP — five files quote 69.8%)

**Resolved in `c632027`.** Four files corrected to 65.2%, each now carrying the
recipe (200 frames of seq 08) rather than a bare percentage.
`research-log.md:402` was **NOT** a defect after all — see the note below.

### ⚑ CONFIRMED FOLLOW-UP — five files still quote 69.8%

Not a maybe. Each needs the same correction (÷14 → ÷15; `other-ground` has a
real computed 0.0% IoU over 150 GT points, not insufficient data, so it counts):

| file | line |
|---|---|
| `docs/handover-2026-09-02.md` | **23** and **169** |
| `docs/demo-runbook.md` | **229** |
| `docs/perception-dashboard-summary.md` | **150** ← JP's lane |
| `docs/research-log.md` | **402** |

~~`research-log.md:402` is the odd one — the *same document* proves 69.8% wrong
at line 430 and still quotes it at 402.~~

**Withdrawn 2026-09-12: 402 is not a contradiction.** It says `frnet_eval.py` is
"the script behind the reported 90.3% / 69.8%", which was **accurate when
written** — that was the reported figure at the time, and the same document
corrects it in a later dated entry. Editing a past entry of another dev's
research log to match a later finding would falsify the log. Left alone
deliberately; nothing is owed here.

## New — the 10 Hz diagnosis (`reports/latency-10hz-diagnosis.md`)

**The answer was already in the repo.** Shrestha, 4 Sep, `adb2c73`:

> the 80.78 / 97.72 in the handover is **not comparable** to this — it is the
> **back half on a synthetic sweep**, where the same back half on real seq 08
> data costs 46.32 ms p50.

So the handover's label is wrong in **both** halves: it is not the frame, and it
is not `--seq 08`. The correct whole-frame number exists in the same entry —
**p50 89.18 / p99 100.43, max 109.28, on real seq 08, quiet machine** — and
**misses 10 Hz at p99 by 0.43 ms**. It was never propagated to the handover,
which still read "meets 10 Hz" in its *proven* table.
**(Corrected 2026-09-12 — the handover now states the measured figure, and 10 Hz has moved to *Not proven*.)**

### On the fallback banner you asked me to look for

**It could not have appeared, and no logs survive anyway.**

- No `.log`, no `*_out.txt`, no `scratchpad/` was ever committed — nothing from
  that run exists.
- The banner postdates the run by **10.7 hours**: introduced by PR #32
  (`c6fad5e`), merged `bc11caf` at **2026-09-03 07:33:42 +0530**; the handover
  commit `464ad8b` is **2026-09-02 20:51:13 +0530**. The code that prints it did
  not exist yet.
- Moot regardless — the run was synthetic, and the synthetic path never calls
  `ground` at all.

### I withdrew my overnight claim, and I was wrong twice

1. **The `--no-patchworkpp` hypothesis is wrong.** Shrestha's run had `ground`
   at 12.41 ms p50 — Patchwork++ **was** active. My arithmetic (87.95 ≈ 80.78)
   was coincidence.
2. **"Does not reproduce under any configuration" is not supported.** This
   machine cannot measure whole-frame latency reliably right now — RAM 2.48 GB
   free of 16.9, `MemCompression` holding 649 MB. Identical back-to-back runs:

| command | spread across identical runs |
|---|---|
| synthetic, 100 frames | p50 stable ±2% (44.03/45.56/44.42), **p99 varies 1.9×** (179–339) |
| synthetic, 200 frames | **p50 varies 3.7×** (42.15 → 155.26) |
| real seq 08, 200 frames | p50 107–152, **p99 varies 4.2×** (121.5 → 510.1) |

100-frame p50 is ~3.4× lower *per frame* than 200-frame p50 on identical code —
superlinear in run length, the signature of accumulating memory pressure rather
than compute. **Shrestha's quiet-machine 89.18 / 100.43 is the better estimate
and nothing here should revise it in either direction.** One run on a machine
with >8 GB free would settle it.

## New in `pending-review/`

| file | what it needs from you |
|---|---|
| `r7-readme-counts-draft.md` | Three drafted lengths of the raw-counts framing (full / medium / one-line), plus notes on wording traps and where to place it. **No diff** — you place it. |
| `r3-ring-boundary-under-anisotropy.md` | Implementation-ready design doc, now that I have the real content. |
| `r5-sticky-safety-critical-class-bit.md` | Same. |

### R3 — what to look at first

Both `ring_of` (`lattice.py:111`) **and** `ring_of_into` (`:346`) implement the
rule and must change identically — `ring_of_into` is the allocation-free frame
path, so the nearest-corner test must not add an allocation. And **PR #31 made
`metrics._ring_cells` filter on `ring_of(centre) == ring`** — if the ring rule
moves to nearest-corner, §9.2 scores a different population than the map serves
unless that moves too. Cross-lane, easy to miss. Three open questions listed at
the end of the doc; I did not guess at them.

### R5 — there is room, and one real weak point

`flags` uses **4 of 8 bits** (`include/vrgrid/cell.py:44`), so bits 4–7 are
free and **the 12-byte struct does not grow** — 8.94 MB and every derived ratio
are untouched. But `include/vrgrid/` is the **frozen** directory: one constant
still needs three-way sign-off.

**The weak point is decay.** `frames_since_seen` is *"frames since the cell was
observed"*, not *"since a VRU was observed"* — so on a continuously observed
cell the bit **never decays**, which is exactly the busy near-field
road-dominated cell where a VRU was most likely a transient minority. Three
designs are laid out; **I did not choose between them.** The doc also gives the
test that discriminates them, and recommends the bit be *rendered* before it is
allowed to change any planning verdict.

## Git

```
branch       main
local HEAD   (see git log)
origin/main  5e0ebf3   — still untouched, never fetched, never pushed
```

`vrgrid-26` still never checked. `src/perception/frnet/` still untouched. The
Patchwork++ determinism bug still untouched and still the single test failure.
