# pending-review: R7 README text — raw-counts framing

**File it would touch:** `README.md` (or wherever you place it)
**Applied?** NO — you place it yourself.
**Measurement:** `reports/r7-hazard-miss-rate.md`

Per your decision: no bare percentage. Below is the drafted text. Three
lengths — pick by how much room the spot has.

---

## Draft A — full (≈90 words)

> ### Hazard misses
>
> On an 11 m × 11 m planning window at the end of each sequence, we compare the
> map's drivability verdict against the 5 cm reference map M\*, cell by cell, on
> ground both observed. Of the cells M\* calls non-drivable, the map called
> drivable:
>
> | sequence | missed / non-drivable | 95% CI |
> |---|---|---|
> | 07 | **8 of 19** | 23.1 % – 63.7 % |
> | 08 | **0 of 3** | 0 % – 56.2 % |
> | 00 | **4 of 38** | 4.2 % – 24.1 % |
>
> **These are counts, not a rate.** With denominators of 19, 3 and 38 the
> confidence intervals are 20–56 points wide and all three overlap — the
> sequences cannot be ordered, and "0 of 3" on seq 08 is not evidence of a safe
> map. In the same windows the map raised **71, 4 and 59 false alarms** — ground
> M\* calls drivable that the map refused. It errs toward caution, which is the
> right direction, but the sample is too small for a stable rate.

## Draft B — medium (≈45 words)

> **Hazard misses.** On an 11 m planning window per sequence, of the cells the
> 5 cm reference map calls non-drivable the map called drivable **8 of 19**
> (seq 07), **0 of 3** (seq 08) and **4 of 38** (seq 00). Denominators this
> small do not support a rate — 95 % intervals run 20–56 points wide and all
> three overlap. Quoted as counts deliberately.

## Draft C — one line

> **Hazard misses:** 8 of 19, 0 of 3 and 4 of 38 non-drivable cells called
> drivable on seqs 07 / 08 / 00, on an 11 m planning window each. Sample too
> small for a stable rate — 95 % CIs span 20–56 points and overlap.

---

## Notes on the wording, in case you rewrite it

- **"of 19" carries the whole message.** Any phrasing that leads with a
  percentage and puts the denominator in a footnote loses it.
- **Do not write "0 %" for seq 08 anywhere**, even with a caveat attached. A
  reader's eye takes the number and drops the qualifier, and this one is 0/3
  with an interval reaching 56 %.
- **"11 m window" is load-bearing.** Without it the reader assumes the figure
  covers the route. It covers one square of ground at the vehicle's final pose;
  40 frames of seq 08 is ~80 m of driving.
- **Do not present it as discriminating between schedules.** `5/10/20/40` and
  `5/10/50` give *identical* results on 08 and 00 — an 11 m window sits entirely
  in ring 0/1, which both share.
- **The false-alarm counts are worth keeping** (Draft A). 71 false alarms
  against 19 real hazards on seq 07 is the more interesting fact, and it is the
  safe direction — but it is not free, since each one is ground a planner will
  refuse to route through.

## Placement

I would **not** put this in Key Results — it is not a headline-shaped number
yet. It reads naturally next to the pothole claim, which already uses this exact
framing (*"56–551 cells per sequence, 10× spread, no pattern. A demonstration,
not a rate."*), or under "Not proven". Your call.

## If you want a real rate later

Sweep the planning window along the trajectory and pool, instead of sampling one
placement — the same fix `89d3551` applied to R(S) when it replaced one query
with 64 (*"one query was never an estimator"*). 40 placements on seq 08 puts the
denominator in the hundreds. It needs a decision on placement spacing and
overlap handling first, which is design rather than measurement.
