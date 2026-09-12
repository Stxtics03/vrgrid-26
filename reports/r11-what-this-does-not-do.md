# R11 — What this honestly does not do

One page, so that no reviewer has to assemble it from six documents and no
presenter has to improvise it under a question.

**Nothing here is new.** Every entry already exists in `docs/sih-math.md`,
`docs/known-limitations.md`, `configs/thresholds.yaml` or a `reports/` file; this
consolidates and cites rather than re-deriving. Where consolidating surfaced
something — a stale justification, a limit whose stated blocker no longer
holds — that is flagged inline and marked as such.

**Written:** 2026-09-12, against `main` @ `5cddaa7`. Writing only; no code or
config was changed to produce it.

---

## The five that matter most

### 1. Ring seams — the traversability layer is coarser than the map

`docs/sih-math.md` §7.1. Slope and step are finite differences over
4-neighbours, and two cases have no neighbours to difference:

- **The map edge.** Rings are `side × side` toroidal squares, so rolling the
  array wraps the far edge of the map onto the near one — a north-edge cell
  would take its gradient against ground 100 m south. The border ring of cells
  therefore carries **bit 5 (confidence)** instead of a gradient.
- **Cross-ring boundaries.** A cell on the inner edge of ring 2 has neighbours
  in ring 1 at half the cell size. Resolving that means resampling across a ring
  boundary for a two-cell strip, and it interacts with both rings' toroidal
  offsets. **Not done.**

**What it costs.** A two-cell strip at every ring boundary falls back to "not
enough evidence" rather than getting a real slope/step verdict. The math doc
states the consequence plainly and it is worth repeating rather than letting it
be found: *"the ring seams are the one place the traversability layer is coarser
than the map."*

**Direction of failure: safe.** The strip is caught by the border rule, which
fails conservative. It is a loss of resolution, not a wrong answer.

**Relevant open design work:** `pending-review/r3-ring-boundary-under-anisotropy.md`
documents a *separate* ring-boundary defect — `ring_of` compares an
anisotropically scaled distance against fixed ring half-widths, so a cell's
footprint can straddle a boundary. Different problem, same seam.

### 2. The slope/step baseline is bounded by the scene, and is a no-op on coarse rings

`configs/thresholds.yaml:19-33`. Bits 1 and 2 are differenced over a **fixed
physical baseline** of `baseline_m = 0.50 m`, not over one cell — without that,
the same 12 cm kerb reads as a gradient of 1.200 at 5 cm and 0.240 at 25 cm
against one frozen `theta_max`, so a feature is a wall on the fine rings and
flat ground on the coarse ones.

The baseline is **bounded on both sides by the scene, not by taste**:

| bound | value | why |
|---|---|---|
| lower | **> 0.33 m** | `0.12/tan(20°)` — so a 12 cm kerb reads passable at *every* cell size |
| upper | **< 1.10 m** | `0.40/tan(20°)` — so a 40 cm pothole rim still **fails** |

0.50 m sits in the middle of a window only 0.77 m wide. **Above 1.10 m the
40 cm pothole rim reads as passable** — that is the hazard ceiling, and it is a
property of the geometry, not a tuning choice.

**The real limitation is what happens on coarse rings.** A ring coarser than
`baseline_m / 2` falls back to a single cell, so **the fixed baseline is a no-op
at 40 cm, at 80 cm, and at the 25 cm planning lattice.** The scale-invariance
the baseline exists to provide therefore does not hold on the outer rings — the
place where it would matter most for long-range hazard detection.

### 3. Unknown is passable at a price — and this is a real concession

`docs/sih-math.md` §8.1(b). **Everywhere else in this project unknown fails
safe.** For the planner it cannot: at `P_fill < 2%` per frame most of the far
field has never been observed, so if unknown were impassable no path would exist
for any schedule and R(S) would be **undefined**.

So unknown is passable at price `w_unknown`, and the unknown fraction of each
path is reported beside R(S).

**What it costs, in the doc's own words:** *"Zero regret along a mostly-unknown
path means the sequence was too short to fill the map, not that the coarsening
was free."*

**And the trap next to it, which is worse.** R(S) compared *across* schedules
measures **fill rate, not coarsening**, unless restricted to ground every
schedule observed. Measured: `5/10/20/40` scored **5.803** against uniform-20 cm's
**0.146** — forty times worse, with nothing impassable in either map. The 5 cm
ring holds few returns per cell, so 65% of its cells sat below `n_min`, paid
`w_unknown`, and the planner routed around a map that was merely *sparse*. **A
finer schedule is penalised for resolving finely, by enough to reverse the
result.** With `common_support()` the same comparison reads 1.793 vs 0.146 at 0%
unknown.

**Any ablation quoting R(S) without the unknown fraction beside it is not
interpretable.** This is the single easiest number in the project to quote
misleadingly.

### 4. The variance inflation term `α` is uncalibrated — and its stated blocker is gone

`configs/thresholds.yaml:140`, `docs/sih-math.md` §5.2. Equation (17):

```
σ²_child = σ²_parent  +  κ ‖∇z‖² (c_p² − c_c²)  +  α
```

`alpha_m2: 0.0`, marked **UNCALIBRATED**. §5.2 says it should be calibrated
against the reference map (§9).

**[!] Surfaced while consolidating: the config's reason is stale.** The comment
says calibration is *"blocked on the download"*. **The download is complete** —
seqs 00/07/08 hold 4,541 / 1,101 / 4,071 scans with matching labels
(`reports/latency-gap-investigation.md`, appendix). So `α` is not blocked on
data any more; it is simply **not done**, which is a different status and should
be recorded as one.

**Not a free change, though**, and the config says why: 0 is the only value
consistent with §5.3's *"splitting flat ground costs nothing"* and §5.4's unit
test (c). **Raising `α` means restating both, in the same commit.** That is a
design decision, not a calibration task.

**Also in the same block — `κ` is knowingly 25% low.** `kappa: 0.0625` (1/16) is
§5.2 as written, but (17) multiplies κ by `(c_p² − c_c²)`, not `c_p²`. The stated
geometry gives **1/12** at every refinement ratio; 1/16 under-inflates by 25%.
Kept as documented pending a room decision, and pinned in
`tests/test_splitmerge.py` so the choice stays visible. No theorem changes
either way.

### 5. Per-cell confidence is a margin, not a probability — and its label channel is a floor

`docs/known-limitations.md` §4, `src/grid/confidence.py` (§7.5).

**It is not calibrated.** Nothing has been fitted against outcomes, so **0.6 is
not a 60% chance of anything.** Each of the four channels is a margin with a
stated meaning, combined by taking the weakest.

**The `label` channel is additionally a floor, not an estimate**, and it
saturates in the wrong direction: the Boyer–Moore counter caps at **7**, so a
cell observed 200 times unanimously reports a *lower* class share than one
observed 8 times. `saturated()` flags that regime — the flag exists precisely
because the number is not trustworthy there.

**What binds it in practice.** On seq 08 the binding channel is **geometry** for
rings 0–2; on the synthetic scene it is `label` and `evidence`. Real terrain
sits near the slope and step thresholds and the analytic scene does not.
`known-limitations.md` calls this *"the clearest single argument in the project
for not reporting synthetic numbers"* — and it applies to everything on this
page, not just confidence.

---

## Also on the list

Briefer, with pointers. Not lesser — just already well documented where they sit.

| limit | what it costs | where |
|---|---|---|
| **10 Hz is not established** | Whole frame is 108.65 ms p50 / 127.23 p99 on the one host measured, against a 100 ms budget. p50 is within reach; **p99 is not, and its cause is unlocated.** No agreed reference machine exists, which is the actual gap. | `docs/handover-2026-09-02.md` *Not proven*; `reports/latency-gap-investigation.md` |
| **Seq 08 is not reportable for accumulated quantities** | A systematic 16.1–17.6 cm per-frame registration offset makes M\* itself inconsistent on 08 (per-cell reference sd median 64.5 cm). Per-ring, curbs, potholes and confidence on 08 are all affected. Timing and ablation do not accumulate and are unaffected. | commit `1c7c24d` |
| **Plan regret has no knee** | R(S) is comparable across schedules at a fixed window and *not* across windows. On the longitudinal query the frozen schedules lose to uniform. | `docs/known-limitations.md` §2 |
| **Curbs and potholes have no ground truth to score against** | 8.1–9.1 cm curb heights and 56–551 pothole cells per sequence are demonstrations, not rates. | `docs/known-limitations.md` §3 |
| **Hazard-miss rate is counts, not a rate** | Denominators are **19, 3 and 38**. 95% intervals span 20–56 points and all three overlap; "0 of 3" on seq 08 is not evidence of a safe map. | `reports/r7-hazard-miss-rate.md` |
| **The visibility candidate cap moves a memory figure** | The reported bound depends on a cap that is not part of the schedule. | `docs/known-limitations.md` §5 |
| **Ring 3 carries no class information** | 100% unlabelled on every sequence measured; its RMSE (9–55 cm) is not interpretable as accuracy. | `reports/r1-accuracy-by-class-and-range-band.md` |

---

## [!] Two limits of method, not of the system

These are newer and they are the reason this page exists in the form it does.
They do not limit what the map *does*; they limit **what any number about it can
be trusted to mean.**

### A. A stateful segmenter is inflating a published accuracy figure

`reports/ring1-reproduction-investigation.md`. The Patchwork++ estimator is a
module-level singleton, and re-processing a scan it has already seen changes its
verdict on that scan. Consequences, both measured:

- `test_real_sequence_replay_is_identical` fails — correctly. Two replays in one
  process differ by 1,245 of 1,479,013 points.
- **~18% of the published seq-07 ring-1 RMSE is measurement artifact.** With one
  estimator shared between the M\* build and the map build, the reference and the
  map disagree about which points are ground; making them consistent moves the
  figure 3.60 → **3.04 cm**.

**Until this is fixed, no ring-1 accuracy comparison finer than ~0.5 cm can be
adjudicated.** Not fixed here: the fix is a lifetime-ownership design decision.

### B. Numbers whose harness was never committed cannot be checked

Twice in two sessions a published figure turned out to be unverifiable because
the script that produced it was session scratch:

- **p50 80.78 / p99 97.72 ms** — no log, no artifact, no script, no method in
  the commit. Reproduces to 1.1% as a *synthetic* back-half benchmark
  (`timing_table.py --cells 910000`), so the number was probably sound and only
  its label was wrong — but that cannot be confirmed.
- **Seq 00 ring-1 RMSE 6.77 cm** — differs from a re-measurement by a
  **61–89 scored-cell population difference**, and the harness that would
  explain it (`scratchpad/r1_accuracy_by_class.py`) has never existed in the
  repository.

In both cases the figure itself is probably fine. **The missing artifact is the
defect.** A harness that produces a number a report will quote is a deliverable,
whatever its filename says — and the cheapest fix available to this project is
to commit them.

---

## What is *not* on this list

Things that were limitations and are now closed, so that nobody re-raises them
from a stale document: the elevation/ghost-removal bug (found, root-caused,
fixed), both plan-regret metric-semantics defects (fixed 2 Sep), the eval
harness height datum (fixed for 07; 08's cause found and it was the pose file),
§9.2's whole-window ring scoring (fixed), and the 19-class fit (resolved 1 Sep
by the 5|3 re-split). Each is recorded with its verification in
`docs/known-limitations.md`.

Also closed, and on the record as rejected rather than untried: **the
`num_iter=2` latency tradeoff**. It buys 5.42 ms and costs 19–54% of ring-0
RMSE concentrated on slopes — measured, not assumed
(`reports/numiter-tradeoff-accuracy-cost.md`).
