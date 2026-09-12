# IIIT Hyderabad — IDD-3D access

*Team Chronicles.exe · SIH26053 · Written 2026-09-05*

---

## ⚠️ Read this before asking your HOD for anything

**IDD-3D is already a public download.** It is listed on IIIT Hyderabad's INSAAN
portal alongside their other datasets — <cite index="20-1">IDD-3D Dataset (236 GB)</cite> — at
`insaan.iiit.ac.in`.

Their datasets are released through a registration and usage-agreement flow, not
through institutional correspondence. **So for the data itself, an HOD letter is
the wrong instrument** — it will slow you down rather than speed you up, and it
uses institutional goodwill you may want later for DRDO.

**Do this first:**

1. Register an account at `insaan.iiit.ac.in`
2. Accept the usage terms (read the publication clause — SIH is public)
3. Download

That is the whole process, and a student can do it today.

⚠️ **236 GB.** Nearly three times your SemanticKITTI download. Check what the
release is split into before starting — you almost certainly want a subset, the
same way you only need sequence 08 on the AWS instance.

⚠️ The toolkit repo `github.com/shubham1810/idd3d_kit` currently reads
<cite index="24-1">"Toolkit code, Data demos and Dataset coming soon!"</cite> — so the loader code may be
incomplete even though the data is up. Budget for writing your own reader.

---

## 1. What to actually ask for — and it isn't the data

The three things vrgrid needs that **3D bounding boxes do not provide**:

| What we need | In the public release? | Without it |
|---|---|---|
| **Per-frame ego-poses** | unknown — verify | **we cannot build a map at all** |
| **Sensor spec: Δφ, mounting height h_s** | unknown — verify | **we cannot derive a ring schedule** |
| Per-point semantic / motion labels | ❌ boxes only, 17 categories | no semantic layer; geometry-only |

**Items 1 and 2 are hard blockers.** Our pipeline accumulates a map across frames,
which requires poses, and our resolution schedule is *derived* from `s_rad(r) =
r²·Δφ / h_s` rather than chosen. Without both, the dataset is unusable no matter
how good it is.

**So: download first, check whether poses and a sensor spec are in the release,
and only write to anyone about what's actually missing.** Asking for things that
turn out to be in the tarball is the fastest way to look like you didn't look.

---

## 2. The right instrument: a direct email to the authors

If poses or the sensor specification are absent, this is a **researcher-to-researcher
question**, not an institutional request. A short, specific email from a student
gets answered faster than a letter from a Principal, because it lands with the
person who actually knows.

**Contacts**, published on the paper:

| | |
|---|---|
| Shubham Dokania (first author) | `shubham.dokania@research.iiit.ac.in` |
| Anbumani Subramanian | `anbumani@iiit.ac.in` |
| Prof. C.V. Jawahar | `jawahar@iiit.ac.in` |

Write to the first two; CC Prof. Jawahar only if there's no reply after ~2 weeks.

### Draft — keep it this short

> **Subject:** IDD-3D — ego-poses and LiDAR sensor specification for a mapping application
>
> Dear Shubham / Dr. Subramanian,
>
> I'm a student at \<INSTITUTION\> working on adaptive-resolution LiDAR elevation
> mapping, under Smart India Hackathon problem statement SIH26053. We've
> downloaded IDD-3D from the INSAAN portal and would like to evaluate our method
> on it, since unstructured Indian road scenes are exactly the setting our work
> targets and no public dataset we currently use represents them.
>
> Our method accumulates an elevation map across consecutive frames, and its cell
> resolution is derived analytically from the sensor's beam geometry rather than
> chosen. Two things we could not locate in the release:
>
> 1. **Per-frame ego-poses** for the LiDAR sequences — and if available, the
>    convention used (source frame, destination frame, and whether from GNSS/INS
>    or SLAM).
> 2. **The LiDAR sensor specification** — vertical angular resolution, beam
>    count, vertical field of view, and mounting height above ground.
>
> The second is the more important of the two: our ring boundaries follow
> `s_rad(r) = r²·Δφ/h_s`, so given Δφ and mounting height we can recompute the
> schedule for your platform even before processing any data.
>
> If poses are not part of the release, we'd also be glad to know whether
> odometry was recorded at capture time, or whether registering the sequences is
> left to the user.
>
> Our implementation is open source at `github.com/Stxtics03/vrgrid`, and we'd be
> happy to share results on IDD-3D with your group. We'd cite the WACV 2023 paper
> in any published work.
>
> Thank you for making the dataset available — it's the only Indian LiDAR dataset
> of its kind that we're aware of.
>
> Best regards,
> \<NAME\>, \<PROGRAMME\>, \<INSTITUTION\>
> \<email\> · \<phone\>

**Why this works:** it shows you downloaded the data, names exactly what's
missing, explains *why* you need it in one line of maths, offers something back,
and can be answered in two sentences. That gets a reply.

---

## 3. If an institutional letter is still wanted

Some HODs prefer to route these formally, and there's a legitimate case for it —
a potential collaboration with IIIT-H's mobility group is worth more than one
dataset. **But send it as a collaboration approach, not a data request**, because
the data is already public and asking for it formally reads as not having
checked.

> **Subject:** Academic collaboration enquiry — LiDAR mapping research using IDD-3D
>
> Respected Prof. Jawahar,
>
> I am writing from \<INSTITUTION\> regarding a student research project in
> adaptive-resolution LiDAR elevation mapping, developed under Smart India
> Hackathon problem statement SIH26053.
>
> The team has developed a memory-bounded 2.5D mapping method in which map
> resolution is derived from the sensor's beam geometry rather than selected
> empirically, achieving a 21.5× reduction in map memory against a uniform grid
> at equivalent near-field accuracy. The work is currently validated on the
> SemanticKITTI benchmark.
>
> Having reviewed IDD-3D (Dokania et al., WACV 2023), we consider it the most
> relevant public dataset for evaluating whether our method holds in unstructured
> Indian traffic conditions, which are substantially denser than the European
> scenes our current benchmark represents. We have accessed the dataset through
> the INSAAN portal.
>
> We are writing on two matters. First, to enquire whether per-frame ego-poses
> and the LiDAR sensor specification are available alongside the released
> annotations, as our method requires both. Second, to ask whether your group
> would have interest in the results — we would be glad to share our technical
> report and measurements on IDD-3D, and our implementation is open source.
>
> A student from the team, \<NAME\> (\<email\>), has separately written to
> Mr. Dokania regarding the technical specifics.
>
> Thank you for your consideration, and for making this dataset publicly
> available.
>
> Yours sincerely,
> \<NAME\>, \<DESIGNATION\>, \<INSTITUTION\>

---

## 4. How this differs from the DRDO request

Don't merge them. Different custodians, different instruments, different asks.

| | **IIIT Hyderabad** | **DRDO** |
|---|---|---|
| Data status | **already public**, 236 GB on INSAAN | not public, may be restricted |
| Right instrument | student email about gaps | **institutional letter** |
| Timeline | days | weeks to months |
| Blocking question | are poses and sensor spec in the release? | **can results be published?** |
| If refused | still have the box annotations | fall back to asking for the sensor spec sheet alone |

⚠️ **Do not put IDD-3D in the DRDO letter.** IIIT Hyderabad and DRDO are
unrelated institutions, and asking a defence lab for another university's public
dataset reads as not knowing where the data comes from. First impressions with
CAIR are worth protecting.

---

## 5. What IDD-3D would actually buy us

Realistic, so nobody over-invests.

**What it can support:** ghost removal on the densest public LiDAR traffic data
that exists — <cite index="26-1">3D bounding box annotations for approximately 223k objects across 17 categories, over 5 hours of driving data</cite>, in Hyderabad. Tracked boxes
across a sequence give us moving-vs-static per point, which is all our
dynamic-object path needs.

**The claim it unlocks:** *"our ghost removal was developed on German suburban
roads; here it is on Hyderabad traffic."* That targets the one capability that
gets **harder** in Indian conditions, on Indian data.

**What it cannot support:** semantic segmentation, mIoU, per-point class labels,
or anything involving FRNet. No per-point labels exist.

**Honest effort estimate:** ~7 days in JP's lane — new loader, new pose
convention, new sensor geometry, derive motion from tracked boxes. **This should
not happen in the ten-day cycle.** It competes with R2, which is worth more.

**What to do instead, now:** put one line on slide 6 and in the report.

> *"Our next dataset is IDD-3D (Dokania et al., WACV 2023, IIIT Hyderabad) — the
> densest public LiDAR traffic data available, on unstructured Indian roads. Its
> annotations are 3D bounding boxes rather than point-wise labels, so we would
> use it to evaluate dynamic-object removal specifically rather than semantic
> segmentation."*

At a national competition, naming the Indian dataset, knowing precisely why it
doesn't drop in, and having a targeted plan for it is worth nearly as much as
running it — and costs two sentences instead of a week.
