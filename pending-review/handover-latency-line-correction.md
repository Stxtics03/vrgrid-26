# pending-review: corrected latency line for `docs/handover-2026-09-02.md`

**File it would touch:** `docs/handover-2026-09-02.md:20`
**Applied?** **YES — applied 2026-09-12.** The full version went into
`docs/handover-2026-09-02.md`: the table row, a latency note beneath the
table, and a new "10 Hz" entry in *Not proven, and must not be claimed*.
This file is kept as the rationale record.
**Measurement:** `reports/latency-gap-investigation.md`
**Written:** 2026-09-12, against `main` @ `fac61c2`.

---

## The line as it stands

```
| latency | frame p50 **80.78 ms**, p99 **97.72** — meets 10 Hz | `timing_table.py --seq 08` |
```

Three defects, in order of severity:

1. **The citation does not produce the numbers.** `timing_table.py --seq 08`
   gives p50 105-112 ms on every run, at every frame count, with real
   Patchwork++ confirmed active. A reader checking the claim gets a number ~35%
   higher than the one quoted.
2. **"meets 10 Hz" is not established.** 108.65 ms p50 does not meet a 100 ms
   budget on the host measured. Whether it meets it on another host is
   unknown — see §"On 10 Hz" below.
3. **80.78 / 97.72 is a synthetic back-half figure, not a seq-08 measurement.**
   It reproduces to 1.1% as `timing_table.py --cells 910000` — the synthetic
   path at full candidate occupancy. It is a real measurement of a different
   thing.

## Replacement — full version

> | latency | seq 08 frame **p50 108.65 ms**, **p99 127.23** — see note | `timing_table.py --seq 08 --frames 200` |
>
> **Latency note.** Measured 2026-09-12 on `main` @ `fac61c2`: 200 frames of
> seq 08, schedule `5/10/20/40`, whole frame (perception **and** map — the
> `FRAME` row, not a back-end subtotal). Real Patchwork++ confirmed active by
> banner on the run: no `semantic-class FALLBACK` warning,
> `PatchWorkpp::PatchWorkpp() - INITIALIZATION COMPLETE` present.
> Host: Intel i7-13620H (laptop, 16 logical), 15.7 GB, Windows 11,
> Python 3.13.9, numpy 2.4.4, `pypatchworkpp` 1.4.1 (PyPI wheel). CPU-only —
> `src/gpu/` is kernel-shaped numpy, not CUDA.
>
> **This does not meet the 100 ms budget on this host**, and the figure is
> host-sensitive: the `ground` stage alone costs 20-21 ms here against 12.41 ms
> on Shrestha's machine (`docs/research-log.md`, 4 Sep), a difference large
> enough to change the verdict. 10 Hz is not established on a common reference
> machine and should not be claimed until it is.
>
> p99 is **duration-dependent** — it ranges 115-147 ms across windows of one
> 221-frame run — so a p99 quoted without a frame count and a host is not a
> checkable number.
>
> **RETIRED: the previous figure of p50 80.78 / p99 97.72 ms "meets 10 Hz".**
> It was cited to `timing_table.py --seq 08`, which does not produce it. It
> reproduces to 1.1% as `timing_table.py --cells 910000` — the **synthetic**
> path with candidate cells raised to the schedule's full allocated slot count
> — i.e. a mislabelled synthetic benchmark result, not a seq-08 measurement.
> The original run itself is unrecoverable (no log, no artifact, no script, no
> method in commit `464ad8b`), so what was actually run cannot be confirmed;
> the reproduction is strong circumstantial evidence and corroborates
> Shrestha's independent 4 Sep note calling the figure "the back half on a
> synthetic sweep". Full archaeology in
> `reports/latency-gap-investigation.md`.

## Replacement — one-line version, if the table must stay compact

> | latency | seq 08 frame **p50 108.65 ms**, p99 **127.23** — **does not meet 10 Hz on this host**; see `reports/latency-gap-investigation.md` | `timing_table.py --seq 08 --frames 200` |

With a single footnote: *the earlier 80.78 / 97.72 figure is retired — it was a
synthetic back-half benchmark (`--cells 910000`), not a seq-08 measurement.*

## On 10 Hz — what I am and am not asserting

**Asserting:** on the host above, seq 08 runs at 108.65 ms p50 with real
Patchwork++, and that misses 100 ms.

**Not asserting:** that the project misses 10 Hz in general. Shrestha's
`ground` is 8-9 ms faster than this host's, and a 221-frame windowed sweep here
reaches **100.59 ms p50** in its best window, so a faster host plausibly lands
under budget. **The claim is untested on a common machine, which is the actual
gap.** Fixing it means one agreed reference host and one agreed command, not a
better number.

## The general defect worth fixing beyond this line

Every latency claim in the docs should carry: the exact command **including
`--cells` and `--frames`**, whether the figure is whole-frame or a subtotal, the
frame window, and the host. The current line carries one of five and that one is
wrong. The same audit is worth running over the other performance numbers — the
two `timing_table.py` paths produce very different figures from similar-looking
commands (`--seq` is whole-frame with a `share` column; the synthetic path is a
back-end subtotal with `owner` and `MB/frame`), and nothing in the output labels
which is which.

## Note on scope

**Update 2026-09-12: the whole pass is now done.** Retiring a headline number is
the same class of change as the mIoU correction and wanted the same treatment —
fix the line, then fix every other file quoting it **in the same pass**, so no
new contradiction is created. That is what was done; the table below records the
outcome per file rather than the plan.

**Seven files quote `80.78`.** (An earlier draft of this note said two — that was
wrong; here is the grep.)

| file | what it says | needs |
|---|---|---|
| `docs/handover-2026-09-02.md:20` | the source claim | **DONE** — row + latency note + new *Not proven* entry |
| `reports/r9-per-stage-latency-and-memory.md:83,92,100` | quotes the claim, then infers it was measured with `--no-patchworkpp` | **DONE** — inference marked WITHDRAWN in place (`23648e9`) |
| `reports/latency-10hz-diagnosis.md` | my earlier diagnosis | **DONE** — SUPERSEDED banner, naming what it got right and wrong |
| `MORNING-SUMMARY.md:45,272,298` | quotes it as the open question | **DONE** — marked resolved, pointed at the new report |
| `reports/latency-gap-investigation.md` | the archaeology | correct as-is |
| `pending-review/handover-latency-line-correction.md` | this file | — |
| `docs/research-log.md:456` | Shrestha's own note, which already says the figure is not comparable | **left alone deliberately** — his file, and he is right; see the tension below |

### [!] `r9-per-stage-latency-and-memory.md:100` contains a withdrawn inference

It currently reads:

> **the logged figure is consistent with having been measured with
> `--no-patchworkpp`** [...] 87.95/106.20 is close to 80.78/97.72

**That inference is wrong and was already withdrawn.** Shrestha's own run has
`ground` at 12.41 ms, which means Patchwork++ *was* active, and the
`--cells 910000` reproduction explains the number without any fallback. This is
a stale claim standing in a committed report and it should be corrected in the
same pass as the handover line, not left to be found later.

### A real cross-document tension, not mine to resolve

`docs/research-log.md:456` states **"the median meets 10 Hz with 10.8 ms to
spare; the p99 is 0.43 ms over"** — that is Shrestha's own whole-frame
measurement (89.18 p50 / 100.43 p99), not the 80.78 figure, and it is a
*different* claim from the handover's. It disagrees with my 108.65 / 127.23 on
the same sequence and code.

Both may be correct on their own hosts — that is exactly the ~1.7x `ground`
difference documented in `reports/latency-gap-investigation.md`. **It should not
be silently reconciled by editing either number.** It is the clearest argument
for the actual fix: one agreed reference host, one agreed command, one number.
