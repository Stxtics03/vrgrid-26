# JP — scope, script, and tonight's checklist

*Personal brief. Audited against `main` @ `8882ec3`, 2026-09-05. Read
`01-CRITICAL-FIXES.md` and `06-DECK-AND-SCRIPT-REVIEW.md` first for the
team-level items; this file is only what lands on you.*

---

## 1. What you own

`src/perception/` and `dashboard/` — everything from the raw `.bin` file to the
point where returns hand off to Shrestha's binning, plus the Rerun app that draws
all of it.

| Area | Files |
|---|---|
| Loader, pose selection | `loader.py` — `POSE_SOURCE_BY_SEQUENCE`, `read_calib` |
| Coordinate transforms | `transforms.py`, and `docs/frames.md` is yours |
| Range image | `range_image.py` — 64 × 512, and it is the **authoritative** azimuth convention |
| Semantic + motion labels | `semantics.py` — GT from raw `.label` |
| Ground segmentation | `ground.py` — Patchwork++, with a loud fallback |
| Reflectivity | `reflectivity.py` |
| The DL model | `frnet/` — deliberately frozen as a reference port |
| Visualisation | `dashboard/` — every scene in the demo |

**One thing worth knowing about your range image:** it is authoritative for the
whole project. Shrestha's `visibility.py` gathers out of your image, and his
`spherical_project` ran the azimuth axis backwards for three days because of it —
`u_here + u_JP == W - 1` exactly. If anyone asks about coordinate conventions,
that is your answer to give, not his.

---

## 2. What you present

### a) Slide 3, steps 1–2 — the data path *(~20 s)*

You are the credibility anchor for "this is a real prototype, not a mockup."

⚑ **Updated numbers** — the deck and your own module doc are both stale here:

> "We're on real data, all of it. SemanticKITTI is complete on disk — **43,552
> scans, 84.8 gigabytes, all 22 sequences**, with point-wise labels on 00 through
> 10. Each frame goes through a transform, a 64-by-512 range-image projection,
> deskew, and Patchwork++ for ground segmentation. Semantic classes and the
> moving-object flags come straight from the raw label files."

*(The deck says "sequences 00 / 07 / 08" and `src/perception/CLAUDE.md` says
"00, 07, 08 only (~40 GB)". Both predate the full download. Your accuracy result
now spans eleven sequences — do not understate it.)*

### b) The demo — you should drive it

It is your module and you know what every entity in the panel is. Two moments
where that shows:

**The blind cone.** Point at the red circle. Say it out loud: 3.74 m, and it is
`unknown`, never `free`. Three occupancy states, and `world/map/free` and
`world/map/unknown` are separate entities on purpose. A panel that hears you
distinguish those knows you have thought about what the robot does not know.

**The ghost toggle.** You can toggle `world/ghosts` at the point-cloud level with
the eye icon inside a single recording, which is more convincing than switching
between two windows.

⚠️ Keep `--show-ghosts` terminal output off screen — it prints `0 occupied cells,
0 cleared, 0 protected` because that counter only fills inside the ghost-removal
branch. Harmless, and not a thing to explain live.

### c) The FRNet answer, when "where's the AI?" comes

Entirely yours, and it is the best unused material in the project. Full wording
is at the end of `07-CORRECTED-SCRIPT.md`. The short shape:

Ported it from ~15% to **90.3% point accuracy / 65.2% mIoU** on 200 held-out
frames of seq 08, against the paper's 73.3%, by finding three divergences.
Then **kept it out of the pipeline on purpose**, so segmentation error cannot
contaminate the mapping result.

**Land the last clause.** It reframes "nothing is trained" from an absence into
experimental discipline, and it is the part judges remember.

---

## 3. Questions that route to you

| Question | Your answer |
|---|---|
| **"Why SLAM poses on 00 and 08?"** | GT puts the same road 16.6 cm apart frame-to-frame on 08 — consistently, so a systematic offset not drift. But per-frame agreement is a *weak predictor*: 00 disagrees by only 2.27 cm/frame yet accumulates −13.95 cm of bias by ring 3, while 03 at 1.97 cm/frame accumulates −0.80. So the override list is chosen on **accumulated** bias, only where there's a measured win, and pinned in `test_only_08_needs_the_slam_poses`. Sequence 06 was tested the same way and is a wash, so it stays on GT. |
| **"How do you segment ground?"** | Patchwork++, wired in not reimplemented. If it's missing the pipeline falls back to a semantic-class mask and says so loudly — the proxy admits terrain and embankments, so it isn't a silent degradation. |
| **"Why 64 × 512 and not 64 × 2048?"** | FLARES — sub-cloud range representations improve both runtime *and* segmentation accuracy over full sweeps in memory-constrained settings. |
| **"Do you use intensity?"** | Yes, but KITTI's is already firmware range/incidence-compensated, so we deliberately don't apply the raw-power `·r²/cos` normalisation to it — it saturated 62% of near-field road at the byte rail. The eq-(31) path is retained for sensors that need it. |
| **"How do you know your frames are right?"** | `docs/frames.md`, plus `FrameGuard` checks frame 0 **and** the first frame ≥10 m from the start. A KITTI `poses.txt` begins at the identity by construction, so on frame 0 the right and wrong compositions agree — a guard that only checked frame 0 would have passed every sequence regardless of convention. |
| **"Where's the deep learning?"** | The FRNet story above. |
| **"Isn't ground-truth labelling cheating?"** | It isolates the mapping contribution from segmentation quality. A poor coarsening ratio can't be blamed on a mis-segmented kerb, and a good one can't be credited to a strong segmenter. The model is reported alongside, never swapped in. |

**The `FrameGuard` answer is your strongest.** A guard that *could not fire*,
found and fixed, is exactly the kind of detail that reads as rigour rather than
luck. Have it ready even if nobody asks — it fits anywhere frames come up.

---

## 4. What you must not say

| ❌ | ✅ |
|---|---|
| "69.8% mIoU" | **65.2%**, over the 15 classes present. The 15 per-class IoUs sum to 977.7; someone divided by 14, dropping `other-ground`. |
| "98.3% point accuracy" | That's **one frame** (seq 00, frame 43), a port check. The reported figure is **90.3%** over 200 frames of seq 08. |
| "FRNet doesn't work" / "non-functional" | It works. It's excluded **by choice**. |
| "Sequences 00, 07, 08" | Eleven labelled sequences for the accuracy result; all 22 on disk. |

⚠️ **Two of these are in your own files**, and a judge browsing the public repo
can find them. See §5.

⚠️ **Do not demo the ground layer on the fallback.** If you see
`[!] ground: SEMANTIC-CLASS FALLBACK`, Patchwork++ isn't installed. Skip that
scene rather than explain it — the proxy includes terrain and admits embankments,
so the ground surface on screen would be wrong.

---

## 5. Tonight — six items

**1. Fix the two figures in your own files.** *(10 min)*

```
src/perception/CLAUDE.md:9      "98.3% point accuracy, 69.8% mIoU"
src/perception/semantics.py:14  "98.3% point accuracy on seq 00 frame 43, 69.8% mIoU"
```

Both should read: **90.3% point accuracy and 65.2% mIoU over 200 frames of
seq 08** (with 98.3% identified as the single-frame port check, if kept at all).

**2. Fix `semantics.py:295`.** *(2 min)*

```python
def get_frnet(...):
    """Disabled -- the standalone FRNet port is non-functional. See _PORT_BROKEN."""
```

This is in code a judge might open, and it contradicts the 90.3% you'll be
quoting on stage. Reword to say the helper is disabled **by design** because
labels come from ground truth, not because the port is broken.

**3. Update the dataset line in `src/perception/CLAUDE.md`.** *(2 min)*
"sequences 00, 07, 08 only (~40 GB)" → all 22 sequences, 84.8 GB, labels on 00–10.

**4. Confirm Patchwork++ on the presenting machine.** *(15 min — do this first
if the machine isn't yours)*

This is **the single most likely demo failure.** `pip install pypatchworkpp`
fails at every published version — the sdist's CMake fetches
`.../tags/v${CMAKE_PROJECT_VERSION}.tar.gz`, the variable is empty under
scikit-build-core, GitHub 404s. Build from the clone:

```bash
git clone --depth 1 https://github.com/url-kaist/patchwork-plusplus.git
.venv/bin/pip install ./patchwork-plusplus/python
```

Then verify no `SEMANTIC-CLASS FALLBACK` banner appears.

**5. Sign off the pose-source change.** *(10 min)*
`POSE_SOURCE_BY_SEQUENCE = {"00": "slam", "08": "slam"}` was changed in your lane
without discussing it with you (handover, JP item 1). You will be asked about it
on stage. Read the eleven-sequence table in `test_only_08_needs_the_slam_poses`
so you can defend it as yours.

**6. Bake the demo.** *(~5 min)*

```bash
./scripts/demo.sh check     # must end "OK -- the pipeline runs on real data."
./scripts/demo.sh bake      # ~3 min, six .rrd files, ~1.2 GB
ls -lh demo/
```

Copy `demo/` and the Rerun viewer to the presenting machine. Playback needs
nothing else — no venv, no dataset, no 84.8 GB.

---

## 6. Not tonight, but have the answer

**The frozen `frnet/` directory.** Shrestha's 3 September note found that
`frustum_encoder.scatter_max` / `scatter_mean` are `for i in range(dim_size)`
loops — ~25,000 iterations over a 124,000-row tensor, seven calls per forward,
10.5 s/frame with ~90% of it in that loop. He measured a native
`torch.scatter_reduce_` replacement at **1408× (max) and 541× (mean)** on CUDA
and **left the decision to you**, because the directory is deliberately frozen as
a reference port.

Nothing needs doing before tomorrow. But if asked *"why is your inference ten
seconds a frame?"*:

> "It isn't, behind `--fast-scatter` — we shim the reductions at runtime rather
> than editing the port, because the port is frozen deliberately so the reported
> numbers can't move underneath us. `scatter_max` is bit-identical either way;
> `scatter_mean` differs by two float32 ulp on CUDA because the native kernel
> sums in a different order and float addition isn't associative, and our
> verifier gates it at a stated ulp bound rather than claiming a bit-identity
> that isn't there."

One trap in that shim worth knowing if you ever apply it permanently:
`frnet_backbone` does `from .frustum_encoder import scatter_max` at import, which
**binds the function object**. Rebinding only the encoder's copy leaves five of
the seven calls on the slow path, and the run looks disappointing rather than
broken.
