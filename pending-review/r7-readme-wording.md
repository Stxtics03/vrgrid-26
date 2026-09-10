# pending-review: R7 hazard miss rate — README wording

**File it would touch:** `README.md`
**Applied?** NO — you asked to decide wording and placement yourself.
**Full measurement:** `reports/r7-hazard-miss-rate.md`

## My recommendation: **do not put a percentage in the README**

I was asked to compute this and I did. Having computed it, my honest advice is
that **the headline number should not ship as a rate**, because the
denominators are 19, 3 and 38 cells:

| seq | rate | 95% CI | what it actually is |
|---|---|---|---|
| 07 | 42.11% | [23.1%, 63.7%] | 8 of 19 cells |
| 08 | 0.00% | [0.0%, 56.2%] | 0 of 3 cells |
| 00 | 10.53% | [4.2%, 24.1%] | 4 of 38 cells |

Three sequences, 42 points apart, **all three intervals overlapping**. And each
covers a single **11 m × 11 m** patch at the vehicle's final pose, not the
route. A README line saying *"hazard miss rate: 10.5%"* would be defensible
arithmetic and misleading English — and "0.00% on seq 08" would be actively
dangerous to quote, since its interval reaches 56%.

This is the same shape as the pothole claim the handover already handles
correctly: *"56–551 cells per sequence, 10× spread, no pattern. **A
demonstration, not a rate.**"*

## Three options, in the order I'd rank them

**Option A — say nothing in the README yet, fix the estimator first.**
Sweep the planning window along the trajectory and pool, exactly as `89d3551`
did for R(S) when it replaced one query with 64 (*"one query was never an
estimator"*). 40 placements on seq 08 puts the denominator in the hundreds and
makes a real rate possible. Cost: a placement-spacing decision plus a re-run.
**This is what I would do.**

**Option B — report it as counts, not a rate.** Something like:

> **Hazard misses.** On an 11 m planning window at the end of each sequence, of
> the cells M\* calls non-drivable, the map called **8 of 19** drivable on
> seq 07, **0 of 3** on seq 08 and **4 of 38** on seq 00. Denominators this
> small do not support a rate — quoted as counts deliberately.

Honest, shippable tonight, and immune to the "0%" trap.

**Option C — put it under "Not proven".** The handover already has that
section, and this fits it better than it fits Key Results.

## What must NOT be said, whichever you pick

- ❌ *"0% hazard miss rate on seq 08"* — 0/3, interval to 56%.
- ❌ any single cross-sequence figure — they differ by 42 points.
- ❌ anything implying it discriminates between schedules. `5/10/20/40` and
  `5/10/50` return **identical** results on 08 and 00; the window sits entirely
  in ring 0/1, which both share.

## Worth pairing with it

False alarms run 4–73 cells. On seq 07 that is **71 false alarms against 19
real hazards** — the map is far likelier to invent a hazard than to miss one.
That is the safe direction and is arguably the better story, but it is not free:
each one is ground a planner will refuse to route through.

**No diff attached** — this is a wording and placement decision, and the
recommendation is "not yet", so there is nothing to apply.
