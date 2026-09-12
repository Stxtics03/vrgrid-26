# The research shelf — Pratyushi

*Reading for this cycle, annotated with **why** each item is here and **what to
extract from it.** Ordered by when it is needed, not by importance.*

**The job is not to read everything.** It is to be able to answer, for every
technical decision Shrestha makes, *"here is the published work this rests on,
and here is where we differ."* A panel that hears a citation next to a design
choice believes the choice.

**Working convention:** one research-log entry per item read, in the existing
append-only format, with a two-line verdict — *what it says* and *what we take
or reject.* An unread paper in a bibliography is worse than an absent one,
because it invites a question with no answer behind it.

---

## §1 — Before Day 1: what we are actually doing

### The project's own documents, in this order

| | Why |
|---|---|
| `docs/gpu-lane/00-WHERE-WE-ARE.md` | the whole project, from scratch |
| `docs/known-limitations.md` | every root-caused defect. **The most valuable document in the repo.** |
| `docs/research-log.md` §Sep entries | how the team writes findings — match this format |
| `docs/sih-math.md` §1.2, §1.4, §6.1–6.2, §872 | beam geometry, detectability, the ring lattice, the 10.3 MB bound |
| `src/gpu/CLAUDE.md` | the module contract you are about to help change |

⚠️ **`sih-math.md:872` is where the 10.3 MB figure comes from**, and it is the
row that reconciles against the allocator's 29.06 MB. Read the derivation before
writing the four-row table (`01-THE-LANE.md` §3) — you need to be able to say
what each row *counts*, not just what it equals.

### The competitor review

Read §8 first — *"what not to change"* — then §3, §4, §6. §6 is the largest
opportunity in the document and it is entirely a reporting change.

⚠️ **Two things in it are stale.** Rule 5's R(S) figures (5.803 / 0.146 / 1.793)
predate the 2 September metric fixes. And §7.2 says we have no published latency
table — we do now, in the research log at line 454. Note both in your log entry
so nobody quotes the PDF verbatim into the report.

---

## §2 — Days 1–2: reporting, which is the cheapest win we have

The review's R1/R7/R8/R11 are under two person-days combined and change how every
number in the submission reads. These are the sources behind the *habits*, not
the numbers.

**Rule 1 — never publish a scalar accuracy.** The canonical statement of why is
the class-imbalance literature; for our purposes the review's own §6.2 argument
is enough: *a classifier answering "drivable everywhere known" lands near 88.8%
without doing anything.*

**What to extract:** the per-class-per-range-band table format, with **counts in
every cell**. The counts are what stop an unstated "enough examples" filter from
being invisible — which is exactly what the review diagnoses in §6.5.

**Rule 3 — stage attrition.** The transferable lesson: their network is 97.5%
accurate and system pedestrian recall is 0.425, because **the recall ceiling is
set upstream of the thing being measured.** Ground removal loses 29.6% of car
points; clustering discards 87.4% of clusters before inference.

**What to extract:** the four-column table (entering / surviving / loss / note),
and the argument that any accuracy number without its attrition is measuring the
wrong stage. This is the format Shrestha instruments on Day 7.

**Rule 5 is ours alone** — R(S) per ring and as a function of frames since first
observation. Our own §1.3 already demands this in stronger language than the
review does. Nobody else in this problem statement will have that curve.

---

## §3 — Days 2–4: deterministic GPU reduction

**The core technical reading of this cycle.** Shrestha's claim is that integer
fixed-point makes the determinism guarantee survive the port; your job is to find
the published grounding for it and for the counter-case.

### Essential

**CUDA C++ Programming Guide** — the `atomicAdd` section, and Appendix on
floating-point. Read specifically: which `atomicAdd` overloads exist per compute
capability, and the statement on float non-associativity.
`docs.nvidia.com/cuda/cuda-c-programming-guide/`

**What to extract:** the exact wording NVIDIA uses about float atomics and
ordering. Quote it in our report — a vendor statement is stronger than our
assertion.

**Goldberg, D. (1991).** *What Every Computer Scientist Should Know About
Floating-Point Arithmetic.* ACM Computing Surveys 23(1).
The canonical citation for non-associativity. One paragraph of it does a lot of
work in a report.

**Whitehead & Fit-Florea (2011).** *Precision & Performance: Floating Point and
IEEE 754 Compliance for NVIDIA GPUs.* NVIDIA whitepaper.
Specifically about GPU float behaviour and why reductions differ run to run.
**This is the closest published statement to the problem we avoid.**

**Demmel & Nguyen** — reproducible BLAS / ReproBLAS work on deterministic
floating-point summation.
**What to extract:** that the field's answer to this problem is elaborate
(pre-rounding, error-free transformations, fixed-point accumulators) — which
tells you our answer is *the standard one*, arrived at for independent reasons.
That framing is worth a sentence in the report.

### Useful

**cupy documentation** — `cupyx.scatter_add`, memory pool, `RawKernel`.
`docs.cupy.dev`. Read the memory-pool page carefully before R9b; the
`used_bytes()` vs `total_bytes()` distinction is what makes our attribution
honest.

**NVIDIA CUB** — `DeviceSegmentedReduce`, `DeviceRadixSort`. What a hand-written
sorted-scatter would use underneath. Relevant if Shrestha goes to `RawKernel`.

**Determinism in PyTorch** — `torch.use_deterministic_algorithms`. Worth reading
for the list of ops PyTorch *cannot* make deterministic; several are scatter
reductions, which is a nice external confirmation of why this is hard.

---

## §4 — Days 4–6: profiling and measurement

**Nsight Systems** (timeline, `nsys`) and **Nsight Compute** (per-kernel,
`ncu`). The DLAMI ships both.

**What to extract for the report:** occupancy and memory-throughput numbers per
kernel. A per-stage table is good; a per-stage table with *achieved occupancy*
beside it is what a systems-literate judge is actually looking for.

**"How to Optimize Data Transfers in CUDA C/C++"** and **"How to Access Global
Memory Efficiently"** — NVIDIA developer blog. Short, and they are the published
grounding for the SoA choice we made on Day 0. Cite them next to the
structure-of-arrays claim.

**Roofline model** — Williams, Waterman & Patterson (2009), CACM.
**What to extract:** the vocabulary for saying whether a stage is memory-bound or
compute-bound. Visibility cleanup is almost certainly memory-bound (a gather per
cell, little arithmetic), and *saying so with the model behind it* is much
stronger than "it got faster."

---

## §5 — Ongoing: the project's own lineage

Already cited in the deck, but you should be able to speak to each. These are
what protect the novelty claim.

| Work | Why it is in our bibliography |
|---|---|
| **Triebel, Pfaff & Burgard (2006)**, Multi-Level Surface Maps, IROS | the 2.5D lineage |
| **Droeschel, Stückler & Behnke (2014)**, ICRA | **closest prior art.** Cite first, unprompted |
| **Losasso & Hoppe (2004)**, Geometry Clipmaps, SIGGRAPH | the toroidal scroll lineage |
| **Fankhauser et al. (2014)**, CLAWAR | confirms our range-dependent measurement variance σ²(r) = σ₀² + c·r² |
| **Wodtko, Griebel & Buchholz (2023)**, Adaptive Patched Grid Mapping, arXiv:2308.03416 | **merges by inverse-variance averaging, dropping the between-cell term.** Our strongest technical criticism of published work |
| **Hornung et al. (2013)**, OctoMap | the volumetric baseline |
| **Reijgwart et al. (2023)**, wavemap, RSS | the modern volumetric baseline |
| **Lim, Oh & Myung (2022)**, Patchwork++, IROS | our ground segmentation, wired in not reimplemented |
| **Xu et al.**, FRNet, arXiv:2312.04484 / IEEE TIP 2025 | the model we ported |
| **Behley et al. (2019)**, SemanticKITTI, ICCV | the data |

⚠️ **The Wodtko criticism is the single strongest point in our prior-art
analysis** and it is a technical, specific, correct criticism of published work.
Make sure at least two people can state it: dropping the between-cell variance
term makes a merged cell *most confident exactly where it straddles a kerb*.

---

## §6 — If there is time: CARLA

The roadmap adds CARLA as a second independent scene source. **The review's
warning matters more than the tool:**

> *Train on CARLA and report on CARLA and the numbers become uninterpretable.*
> Every accuracy table must carry a SemanticKITTI column beside it, and the
> degradation between them **is the result**, not an embarrassment.

**Read:** Dosovitskiy et al. (2017), *CARLA: An Open Urban Driving Simulator*,
CoRL. Plus the semantic-LiDAR sensor documentation.

**What to extract, and it is a finding rather than a citation:** CARLA's LiDAR is
a raycast against mesh geometry. It returns a point wherever a ray intersects,
with **no dropout on dark, wet, retroreflective or grazing surfaces**, and its
semantic LiDAR supplies per-point labels directly — so a CARLA-trained pipeline
may never exercise the clustering stage that costs 87.4% of clusters on real
data. That is the mechanism behind the review's §6.5 finding of *recall rising
with range*, which is impossible on real LiDAR and which our own §1.2 derivation
explains why.

**Being able to explain why their CARLA curve rises is worth more to us than
generating CARLA scenes of our own.** It demonstrates we understand both sensors.

---

## §7 — Writing convention

Every entry in the research log, same day as the work:

```
### YYYY-MM-DD — <owner> — <one-line finding>

**What was run:** exact command, machine, GPU/driver/CUDA if relevant
**Result:** the numbers
**Verdict:** what we take, what we reject, what it changes
**Supersedes:** any earlier entry this replaces
```

⚠️ **The `Supersedes` line is the one people skip and it is the one that matters.**
This project already carries a 69.8% mIoU that should be 65.2%, `2.45 ms` quoted
as a whole-grid rebuild when it is a non-default pyramid's, and six documents
calling a working FRNet port non-functional — all of them because a correction
landed in one place and not the others.

**Our pair's contribution to that problem is to not add to it.**
