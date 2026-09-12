# Where we are — the whole project, from scratch

*For Shrestha and Pratyushi, starting the post-round cycle. Written 2026-09-05
against `main` @ `8882ec3`, plus the competitor review and the 10-day roadmap.
Read this before `01-THE-LANE.md`.*

---

## 1. What vrgrid is

A LiDAR map for a ground vehicle where **cell size grows with distance from the
vehicle** — 5 cm nearby, 40 cm far out, in concentric square rings — under a
memory budget fixed before the first scan arrives.

The justification is physics, not thrift. Radial ground beam spacing goes as
`s_rad(r) = r²·Δφ/h_s`; with the HDL-64E's Δφ = 0.427° and h_s = 1.73 m that is
centimetres at 5 m and **10.8 m at 50 m**. A uniform 5 cm grid at 50 m is 99.87%
empty in one frame — it stores interpolation, not measurement.

Four ideas, in dependency order:

1. **Rings from beam geometry.** Derivation, not design taste. The strongest
   thing in the project.
2. **Integer lattice.** `i_L = i_fine // k_L`, never `floor(x/0.20)`. Merge uses
   the **law of total variance** (the between-cell term is what everyone drops,
   and dropping it makes a merged cell most confident exactly where it straddles
   a kerb). Split inflates variance and sets a `derived` bit so
   `merge(split(c)) == c` is exact.
3. **The bound is structural.** Everything preallocated; under load the pool
   refuses and evicts rather than growing.
4. **Plan regret.** Score the map by whether it changed the *decision*, not by
   centimetres. Most original idea in the project, and **currently the weakest
   result** — see §4.

## 2. The numbers that are real

| | |
|---|---|
| Map | **8.94 MB** = 745,000 cells × 12 B |
| Total preallocated | **29.06 MB** (map + every frame-path buffer) |
| Ratios | **21.5×** vs uniform 5 cm 2.5D (192 MB), **286×** vs dense 3D (2.56 GB) |
| Accuracy | **ρ ≈ 1.45**, range 1.26–1.59, n = 11 sequences, ring 1 |
| Latency | **p50 89.18 ms / p99 100.43 ms**, 200 frames seq 08, 100 ms budget |
| Ghosts | 13.5% of trail removed, 4.96 M cells cleared, **429,012 spared by the guard** |
| Segmentation | FRNet **90.3% point acc / 65.2% mIoU**, 200 frames seq 08 (paper 73.3%) |
| Repo | 206 commits, CI green |

## 3. ⚠️ There are now **four** memory numbers in circulation

This is the first thing your lane has to fix, because R8 and R9 both depend on it
and R9 is yours.

| Number | Where | What it is |
|---|---|---|
| **8.94 MB** | `README`, `memory_table.py` | the map alone: 745,000 × 12 B |
| **10.3 MB** | `docs/sih-math.md:872` — *"Total bound ≈ 10.3 MB, compile-time"* | map + refinement pool + transient + tracks, as **derived in the maths** |
| **29.06 MB** | `allocate()`, the dashboard counter, `regret_plot.py`'s memory axis | what is **actually committed** at startup, all working buffers included |
| **32.17 MB** | with the conservative pyramid enabled | not default |

The competitor review quotes the 10.3 MB one (*"we make a hard 10.3 MB
compile-time bound claim"*), the README quotes 8.94, and the dashboard shows
29.06. **The maths doc's bound and the allocator's reality differ by 2.8×.**

That is not a bug — the maths bound counts the *representation*, the allocator
counts representation *plus scratch*. But four numbers with no published
reconciliation is exactly the kind of thing R9's "attributed VRAM" section is
supposed to fix, and it cannot be fixed by measuring VRAM. **It has to be fixed
by publishing one table with four rows.** That table is yours, Day 1.

## 4. What is not proven

**Plan regret does not currently favour us.** Sequence 08, 20 frames, 64-query
mean, matched extent:

| schedule | MB | R(S) |
|---|---|---|
| uniform 20 cm | 30.50 | **0.251** |
| **5/10/20/40 (ours)** | **29.06** | **0.488** |
| uniform 40 cm | 18.50 | **0.402** |

Three real defects in the metric were found and fixed on 2 September (a
resolution-dependent confidence handicap; the two sides evaluated on different
lattices, which invented 148 phantom walls; a class penalty charged on one side
only). After all three, uniform 20 cm at comparable memory still plans better.

**The diagnosed cause is the query.** `PLAN_LANE_CELLS` is a single longitudinal
lane down the centre of the window, unchanged since Day 0, with **no hazards on
it.** With nothing real to differentiate the maps, the only thing left is
spurious cost — and fine cells manufacture it, because a 5 cm cell pools fewer
returns than a 20 cm cell, drops below `n_min`, gets flagged low-confidence, and
the planner steers around it. Traced to a single cell: column 16 has one
low-evidence cell, column 17 has none, so the fine schedules sidestep for the
whole corridor.

**So: the fine map detours around a phantom made of its own sparsity.** The query
is the limit, not the metric.

⚠️ **The competitor review's Rule 5 is stale on this.** It says to print
*"5.803 against 0.146 … 1.793 after"* under the money plot. Those are the
**pre-fix** numbers from 29 August. The current table is above. Do not carry the
old figures into the report.

## 5. ⚠️ There is no CUDA in this project

Relevant to you above everyone else, because your pair is named "GPU / CUDA
kernels."

```
$ find . -name "*.cu" -o -name "*.cpp" -o -name "*.cuh" -o -name "*.hpp"
(nothing)

$ ls include/vrgrid/        ← the "C++17 frozen interfaces"
__init__.py   api.py   cell.py
```

`src/gpu/` is **numpy on CPU**. `allocators.array_module()` imports cupy when
`device != "cpu"`, but cupy appears in no test, no script, and no measurement.
Every latency figure was taken single-threaded on an Intel i7-14650HX. The only
thing that touches CUDA is FRNet inference through torch, and FRNet is not in the
mapping pipeline.

The deck currently claims *"CUDA kernels for project, fuse, split, merge"* and a
*"Python 3.11 · C++17 · CUDA"* stack. That claim is checkable and false, and the
deck hands judges the public repo link.

**Your lane is the one that can make it true.** That reframes this cycle: it is
not "add GPU acceleration to a GPU project," it is **"write the GPU
implementation the project has always been designed for."** Everything in
`src/gpu/` was built to the constraints a kernel has — SoA, no allocation in the
loop, deterministic reduction order, a device seam in the allocator. The port is
the payoff on three weeks of discipline.

## 6. The one insight that makes the port viable

**Because heights accumulate as int32 fixed-point, the determinism guarantee
survives the move to GPU for free.**

Float `atomicAdd` on a GPU completes in nondeterministic order, and IEEE addition
is not associative, so a float map differs run to run and you cannot bisect a bug
whose location moves. That is why the project chose integer accumulation on Day 0.

**Integer `atomicAdd` is exact, associative and commutative.** Order does not
matter. So `cupyx.scatter_add` on an int32 target is bit-identical regardless of
how the scheduler interleaves the blocks — and `make test-determinism` should
pass on device without a single change to the reduction logic.

Most projects cannot port to GPU without giving up reproducibility. **You can,
and the reason is a decision already made.** That is both the technical
foundation for this cycle and, honestly, the best thing your pair will have to
say at the finals.

⚠️ It holds only where the accumulator is integer. Anything float — the Kalman
update, variance, `scatter_mean` — needs an explicit audit. See
`03-CUDA-PORT-PLAN.md` §4.

## 7. What the competitor review actually tells us

Eleven recommendations, R1–R11. Read §8 of the PDF first — *"what not to
change"* — because it is the honest summary: **we are ahead on representation
and mathematics by a wide margin**, and behind on one thing the problem statement
names directly, which is a model in the loop.

The three findings that matter most:

**a) The ring-boundary bug is real, and it is ours too under anisotropy (R3/R4).**
Their tier boundary was radial (Euclidean) against a square lattice, so a parent
block near the boundary had children on both sides. 82 overlapping footprints on
KITTI frame 0 — **with zero points lost or double counted.** The partition was
perfect the whole time; the defect was between *footprints*, not point sets.

Our §6.1 uses the Chebyshev norm, so isotropic rings are square annuli aligned to
the lattice and this cannot happen. **Our §6.2 anisotropy divides by a continuous
float** `a_f(v) = clamp(1 + k_f·v/v_ref, 1, 2)`, which puts the boundary at an
arbitrary real position, off the lattice. Same failure, waiting.

⚠️ **Our CI partition test cannot see this.** It asserts each point maps to
exactly one cell *per ring*. This bug leaves the per-ring partition intact and
creates containment *across* rings. New test needed.

**b) Majority voting erases the class the safety case rests on (R5).**
195 road points and 5 pedestrian points must resolve to pedestrian. Boyer–Moore
returns road. And our own §1.4 says a pedestrian at 1.4 m/s clears ring 0 and
ring 1 by motion but **not ring 2** — crossover ~25 m — so beyond 25 m the
semantic layer is the only thing carrying VRUs, exactly where fill rates make a
distant pedestrian a handful of returns in a road-dominated cell. Compounded by
the saturating counter: at C = 7 the Boyer–Moore guarantee is a time constant,
not a theorem.

**c) The reporting change is the largest single opportunity, and it costs a day.**
R1, R7, R8, R11 together are under two person-days and change how every number
reads. Rule 1: never publish a scalar accuracy. Rule 3: report stage attrition,
not terminal accuracy — their 97.5% cluster accuracy coexists with 0.425
pedestrian recall because **the recall ceiling is set upstream of the thing being
measured.**

## 8. Where your lane sits in all of it

The roadmap gives Shrestha + Pratyushi: **GPU / CUDA kernels.** Concretely:

- **R9** (yours outright) — per-stage latency table + attributed VRAM
- **R3/R4 kernel side** — the anisotropic boundary snap, and the
  footprint-disjointness CI test
- **R5 kernel support** — the sticky VRU bit touches fusion
- **AWS provisioning** and reproducing the FRNet numbers on a clean machine
- **Day 6's real question:** does the grid engine plus FRNet-in-loop fit one T4?
- **Day 7:** stage-attrition instrumentation at the kernel level

Read `01-THE-LANE.md` next. It has six things in the roadmap that need resolving
**before Day 1 starts**, three of which are ownership collisions that will cost
days if they are discovered on Day 3 instead.
