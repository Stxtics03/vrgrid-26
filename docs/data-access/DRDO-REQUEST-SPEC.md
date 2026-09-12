# DRDO dataset access — what to ask for

*For the HOD / Principal to forward. Written 2026-09-05.*
*Team Chronicles.exe · SIH26053 · Adaptive Variable-Resolution 2.5D LiDAR Mapping*

---

## ⚠️ Settle this question first, before anything else

**Can we publish results computed on the data?**

SIH is a public competition. The deck, the demo and the repository are all public.
If the data comes with a restriction that says results may not be published, or
that derived figures need clearance per publication, **the dataset is unusable
for this purpose** no matter how good it is.

This is not a detail to sort out at the end. Put it in the first email, because
the answer determines whether the rest of the request is worth making.

Three possible outcomes, and all three are fine:

- **Publishable** → use it, cite it, headline it.
- **Usable but results need clearance** → use it for internal validation only,
  and state in the deck that we validated on restricted data without quoting
  figures. Still worth something.
- **Not shareable** → ask instead for the *sensor specification* alone (§2,
  item 5). That is often unclassified, it is small, and it is the single most
  valuable thing on the list. See §4.

**Realistic timeline:** institutional data requests to a DRDO lab take weeks to
months. This will not land before the finals. Start it anyway — an initiated
request is worth a line on the slide, and this project outlives one competition.

---

## 1. Which lab

**CAIR (Centre for Artificial Intelligence and Robotics), Bengaluru** is the
right first approach. It is the DRDO lab working on autonomous ground vehicles
and robotics, and it is local to us.

Secondary, if CAIR redirects:
- **VRDE** (Vehicles Research & Development Establishment), Ahmednagar
- **R&DE(E)** (Research & Development Establishment, Engineers), Pune
- **CVRDE** (Combat Vehicles R&D Establishment), Chennai

Let the letter name CAIR and ask to be redirected if another lab holds the data.

---

## 2. What we actually need

**Ranked. Items 1, 2 and 5 are mandatory — without any one of them the data
cannot be used at all. Items 3 and 4 determine how much of the project it can
support.**

### 1. Raw LiDAR sweeps ✅ mandatory

Per-point `(x, y, z, intensity)` in **sensor frame**, one file per frame, in any
documented binary or ASCII format.

⚠️ Sensor frame specifically, not a pre-transformed world frame. If the data has
already been ego-compensated we need to be told, because our pipeline applies
that transform itself and would apply it twice.

**Volume:** a few thousand consecutive frames from continuous driving is enough.
We do not need hours. **Sequences matter more than total size** — 2,000
consecutive frames is far more useful than 20,000 scattered ones, because we
accumulate a map over time.

### 2. Per-frame ego-poses ✅ mandatory

A 4×4 transform (or 3×4 row, KITTI style) per frame, **time-synchronised to the
sweeps**, with the convention stated explicitly:

- Which frame is the source and which the destination?
- Is the origin at the sensor or at the vehicle datum?
- What is the source — GPS/INS, SLAM, or a fused solution?

⚠️ **State the convention in writing.** We lost days on KITTI to exactly this:
its `poses.txt` rows are Camera-0 → World_cam, not vehicle → world, and getting
it wrong fails *silently* — the map degrades rather than crashing. We would
rather have the convention documented than reverse-engineer it.

### 3. Labels — any of these, in order of usefulness

- **(a) Per-point semantic labels** — ideal. Even a coarse taxonomy is fine:
  ground / vegetation / structure / vehicle / person is enough for us.
- **(b) Per-point moving/static flag** — this is the one nobody has and the one
  we most want. It drives our dynamic-object removal.
- **(c) Tracked 3D bounding boxes with persistent IDs across frames** — we can
  derive (b) from these ourselves.
- **(d) Nothing** — still usable. We can run geometry-only and report the
  ground-segmentation and mapping path without the semantic layer.

### 4. Calibration ✅ mandatory if the sensor is not at the vehicle origin

Sensor → vehicle extrinsics, as a 4×4 matrix. Plus the **mounting height above
ground**, which we use directly (see item 5).

### 5. Sensor specification sheet ✅ mandatory — and the single most valuable item

| Quantity | Symbol | Why we need it |
|---|---|---|
| Vertical beam count | — | sets the sampling density |
| Vertical angular resolution | **Δφ** | **our ring boundaries derive from it** |
| Vertical field of view | — | upper and lower limits |
| Horizontal angular resolution | Δθ | azimuth sampling |
| Rotation rate | — | frame period |
| Mounting height above ground | **h_s** | **derives with Δφ** |
| Range accuracy vs distance | σ(r) | our clearing tolerance is 3σ(r) |

**Why this matters more than the points themselves.** Our resolution schedule is
not chosen, it is derived: `s_rad(r) = r²·Δφ / h_s` gives the radial spacing
between consecutive beam ground-intersections. For the sensor we currently use
that is 10.8 m at 50 m range. **Given Δφ and h_s for a DRDO platform's sensor we
can recompute the entire schedule for that platform on paper, in an afternoon,
with no data at all.**

If the answer to §0 is "data not shareable," **ask for this table alone.** It is
usually unclassified, it fits on one page, and it lets us state a genuine result:
*"here is the ring schedule our method derives for a DRDO-relevant sensor
configuration."*

### 6. Nice to have, not required

- Terrain type / environment description (paved, unpaved, off-road, semi-urban)
- Any ground-truth surface or elevation reference
- Weather and time of day
- Whether the platform is tracked or wheeled, and typical speed range

---

## 3. What we would do with it, and what we would give back

Worth stating in the letter, because a lab is more likely to release data to a
team that says what it will produce.

**What we would run:**
1. Recompute the ring schedule from their sensor geometry
2. Report our coarsening-justification ratio ρ on their terrain (currently ≈1.45,
   range 1.26–1.59, across eleven SemanticKITTI sequences)
3. Report the memory bound at their platform's operating extent
4. Report per-frame latency against a 10 Hz budget
5. Ghost removal, if any motion labelling is available

**What we would return:** the full technical report, the measured tables, and the
code, which is already public at `github.com/Stxtics03/vrgrid` under an open
licence. No commercial use, no redistribution of their data.

---

## 4. Draft letter

*For the HOD or Principal to adapt onto institutional letterhead. Keep it short —
the specification goes in the annexure.*

---

> **Subject:** Request for access to LiDAR dataset for academic research —
> Smart India Hackathon problem statement SIH26053
>
> Respected Sir/Madam,
>
> I am writing on behalf of \<INSTITUTION\> regarding a student research project
> currently being developed under Smart India Hackathon problem statement
> SIH26053, *Adaptive Variable-Resolution 2.5D LiDAR Mapping for Dynamic
> Environment Perception*, under the Smart Vehicles theme.
>
> The team has developed a memory-bounded elevation mapping method for
> autonomous ground vehicles in which map resolution is derived from the sensor's
> own beam geometry rather than chosen. The work is presently validated on the
> public SemanticKITTI benchmark. To assess whether the method generalises to
> platforms and terrain relevant to Indian defence applications, we would like to
> request access to LiDAR data collected on a DRDO unmanned ground vehicle
> platform, if such data can be made available for academic research.
>
> The specific data elements required are set out in the attached annexure. We
> would note that the sensor specification alone — vertical angular resolution
> and mounting height — would be of substantial value to us even if the point
> data itself cannot be released, as our resolution schedule is derived
> analytically from those two quantities.
>
> We would be grateful for guidance on the applicable usage terms, and in
> particular **whether results computed on the data may be published**, as the
> Smart India Hackathon submission is public. We are willing to work within
> whatever restrictions apply, including limiting the data to internal validation
> without publishing derived figures.
>
> The team would be glad to share its technical report and results with your
> laboratory. The implementation is open source and publicly available.
>
> If CAIR is not the appropriate custodian for this data, we would be grateful to
> be directed to the relevant establishment.
>
> Thank you for your consideration.
>
> Yours sincerely,
> \<NAME\>, \<DESIGNATION\>
> \<DEPARTMENT\>, \<INSTITUTION\>
>
> *Enclosure: Annexure — data specification (1 page)*

---

## 5. The one-page annexure

Attach §2 above, trimmed to the table below.

| # | Item | Required? | Notes |
|---|---|---|---|
| 1 | Raw LiDAR sweeps, per-point (x, y, z, intensity), **sensor frame** | Yes | 2,000+ consecutive frames from continuous driving. Any documented format. |
| 2 | Per-frame ego-poses, time-synchronised, **convention stated** | Yes | 4×4 or 3×4. Source (GNSS/INS, SLAM, fused) noted. |
| 3 | Per-point semantic labels, **or** moving/static flags, **or** tracked 3D boxes | Preferred | Coarse taxonomy is sufficient. |
| 4 | Sensor → vehicle extrinsic calibration | Yes | 4×4 matrix. |
| 5 | **Sensor specification: vertical angular resolution (Δφ), beam count, FOV, mounting height above ground (h_s), range accuracy vs distance** | **Yes** | **Of standalone value even without items 1–4.** |
| 6 | Environment and platform description | Optional | Terrain type, speed range, weather. |

**Point of contact:** \<student name\>, \<email\>, \<phone\>
**Project repository:** github.com/Stxtics03/vrgrid

---

## 6. Follow-up discipline

- **Log the date sent and to whom** in `docs/research-log.md`. If it lands after
  the finals, the next team needs the thread.
- **Do not plan any deliverable around data that has not arrived.** Everything in
  the ten-day roadmap must stand on SemanticKITTI alone.
- **The slide line, if the request is sent:** *"We have initiated a data access
  request through our institution to DRDO CAIR for validation on a defence UGV
  platform."* Accurate, costs one line, and shows the work has a path beyond the
  benchmark.
