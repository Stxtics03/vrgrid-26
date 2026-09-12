# Why this project matters

*For the opening slide, the impact section of the report, and the "so what?"
question. Two minutes of material, three framings, pick by audience.*

---

## The one-paragraph version

Autonomous ground vehicles have to hold a map of their surroundings in memory
while planning through it, at 10 Hz, on hardware that fits in a vehicle. Today
that forces a bad trade: store the world finely and run out of memory, or coarsen
it uniformly and lose the kerb you needed to see. `vrgrid` breaks the trade by
observing that the sensor itself does not measure uniformly — a LiDAR's beams
land centimetres apart nearby and ten metres apart at range — and matching the
map's resolution to where the measurements actually are. The result is a map
that costs **8.94 MB instead of 192 MB**, keeps full 5 cm fidelity exactly where
a vehicle can still be stopped, and has a memory footprint fixed before the first
scan arrives rather than one that grows with the scene.

---

## Framing 1 — for a systems / embedded panel

**The claim: a bound, not an average.**

Most mapping systems report an average memory footprint. That number is useless
for certification, because the failure case is the busy intersection, not the
empty road. `vrgrid` allocates everything at startup — grid arrays, refinement
pool, transient layer, tracked-object list — and nothing in the frame loop grows.
When the scene exceeds what the pool can hold, the correct behaviour is refusal
and eviction, and that is what happens and what is tested.

Verified against a deliberately hostile case: 400 pedestrians, every return
dynamic, every one triggering the semantic refinement gate, all of them small
and close and a metre apart. **20% more returns cost 1.2% more peak memory.**

Why a panel should care: dynamic heap allocation in the perception path is what
produces unpredictable p99 latency spikes, and p99 is what safety arguments are
made on. A system that is fast on average and occasionally slow has dropped a
frame of obstacles. This is the difference between a research prototype and
something that could be argued for in a safety case.

**Supporting detail if pressed:** the map is bit-identical run to run. Heights
accumulate as int32 rather than float, because IEEE-754 addition is not
associative and GPU atomic float adds complete in nondeterministic order — which
means the map changes between runs and you cannot bisect a bug whose location
moves. The determinism test is CI-blocking.

---

## Framing 2 — for a robotics / research panel

**The claim: we measured the compression in the units that matter.**

Every compression paper reports reconstruction error. But a map is not an end in
itself — it exists so a planner can choose a route. The right question is not
"how many centimetres did we lose" but **"did the vehicle make a different
decision?"**

That is what plan regret measures: plan on the compressed map, plan on the 5 cm
reference, and score *both routes on the reference*. Scoring both on the
reference is the invariant that makes it honest — a blurred kerb the compressed
map cannot see produces infinite regret rather than false safety.

**Be straight about the status.** The metric is implemented, three real defects
in it were found and fixed, and on the only planning query implemented so far the
result does not favour our schedules. The query is a longitudinal lane down the
centre of the window, and a lane query structurally cannot reward a map for being
sharp where the vehicle is *looking*. So the contribution here is the
methodology and the machinery, and the result is open.

Presenting that honestly is not a weakness. Decision-sensitive evaluation of map
compression is a genuinely under-explored direction — the nearest work
(Psomiadis et al., ICRA 2024) targets multi-robot communication bandwidth on
generic 2D grids, not automotive elevation mapping under a hard memory bound. A
panel that sees you build the right evaluation and report an inconvenient result
learns more about your rigour than one that sees a clean plot.

**The second research contribution, which does hold:** the coarsening-justification
ratio ρ. Raw RMSE tells you how rough the road was, not what your coarsening cost
— across eleven sequences RMSE spans 5.3× while ρ spans 1.26×. Dividing the
coarsening's information loss by the terrain's own sub-cell variability separates
those, and **ρ ≈ 1.45 (range 1.26–1.59, n = 11)** says the coarsening cost only a
little more than the terrain's own roughness already did.

---

## Framing 3 — for a deployment / national-impact panel (SIH)

**The claim: this is the version of the problem that runs on hardware India
actually deploys.**

Three points, in descending order of how much they land:

**1. Negative obstacles are the Indian road problem, and this project treats them
honestly.** Potholes are the concrete case, and the finding is a physical limit
rather than an engineering shortfall: a 30 cm pothole is invisible beyond
**8.3 m** from a roof-mounted 64-beam LiDAR, because consecutive beams simply
miss it. `s_rad(r) = r²Δφ/h_s` is not negotiable by better software. What
`vrgrid` does is refuse to fabricate: beyond that range cells are marked
`unknown`, never `free`. A uniform 5 cm map that reports `free` at 50 m is not
more accurate — it is confidently wrong, and a planner that trusts it drives into
the hole.

Measured, on all eleven sequences, through the real pipeline: kerbs at ring 0
read **8.1–9.1 cm across every one of eleven recordings**, different dates and
different calibrations, agreeing to one centimetre. That consistency is the
evidence a detector measures something physical.

**2. Memory is the binding constraint on Indian edge deployment.** A Jetson-class
board is what a domestic autonomy stack ships on, and 192 MB of map competes
directly with the perception network for the same memory. 8.94 MB does not.
21.5× is the difference between a map that fits alongside a segmentation model
and one that does not.

**3. Dynamic ghosts are worse on dense, mixed traffic.** A moving vehicle writes
occupancy into every cell it passes through, and those trails accumulate into
phantom walls the planner routes around. That failure scales with traffic
density, which makes it a sharper problem on an Indian arterial than on the
German suburban roads this was tested on. Measured: **13.5% of the trail removed,
4.96 M cells cleared** on sequence 08, with **429,012 cells protected** by the
guard that stops the cleanup eating fences and poles.

---

## What is genuinely novel — the honest version

Do **not** claim you invented foveated grids, elevation maps, or dynamic-point
removal. All three are published, and a panel that hears you claim them stops
listening. Cite Triebel 2006 and Droeschel 2014 *next to your own ring diagram*.
A team that cites the thing it resembles is a team that knows the field.

What is defensibly yours is the **composition**:

1. **A resolution schedule driven jointly by range and semantics, under a hard
   preallocated memory bound.** Each ingredient exists; this combination under a
   compile-time bound does not.
2. **Uncertainty-honest split/merge** via the law of total variance, with a
   provable round-trip property `merge(split(c)) == c`. The nearest published
   adaptive grid (Wodtko et al. 2023) uses inverse-variance averaging, which
   makes merged cells *most confident exactly where they straddle a kerb* — the
   one place false confidence is dangerous. This is a specific, technical, correct
   criticism of published work, and it is the strongest single point in your prior-art
   analysis.
3. **Plan-sensitivity evaluation** — coarsening measured in units of planner
   regret rather than reconstruction error. Methodology contribution; result open.

---

## The closing line

> *"We did not set out to compress a map. We set out to stop storing data the
> sensor never collected, and then to check — in the units a planner actually
> cares about — whether that cost anything. The first part works and we can show
> you the bytes. The second part is where the interesting work still is, and we
> can tell you exactly what is left."*
