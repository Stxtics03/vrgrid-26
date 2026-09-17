# Open items — the master list

Single place for what is outstanding, so nothing falls between sessions.
Assembled 2026-09-12 by reading every file in `reports/` and `pending-review/`
plus `MORNING-SUMMARY.md`, against `main` @ `e4bd731`.

**How to read the status column:** *Decision* = waiting on JP, nothing to do
until then. *Ready* = scoped, could be picked up now. *Blocked* = waiting on
something external or someone else.

---

## 1. Waiting on your decision — nothing proceeds until these are called

| # | item | why it needs you | file |
|---|---|---|---|
| **D1** | **The Patchwork++ singleton lifetime.** Does `segment_ground` take an estimator? Does the module expose a reset? Who owns the lifetime? | Design decision with three real options, none obviously right. **Highest-impact item on this list** — see §2. | `reports/ring1-reproduction-investigation.md` §7 |
| ~~**D2**~~ | ~~**R3 — ring boundary under anisotropy.**~~ **Closed 2026-09-17** — see §4. | | `pending-review/r3-ring-boundary-under-anisotropy.md` |
| **D3** | **R5 — sticky safety-critical class bit.** Which classes (5/6/7 only, or also 1/2)? Which of three decay designs? What is N, and it must live in frozen `configs/thresholds.yaml`? Does it affect traversability, and on which commit? | Five open sub-decisions, listed in the file. Also touches frozen `include/vrgrid/cell.py` — three-way sign-off. | `pending-review/r5-sticky-safety-critical-class-bit.md` §6 |
| **D4** | **R7 README wording** — which of three drafted lengths, and where it goes. | You said you would place it yourself. | `pending-review/r7-readme-counts-draft.md` |
| **D5** | **`alpha_m2` — raise it or leave it at 0.** | Not a calibration task: 0 is the only value consistent with sih-math §5.3 and the §5.4 unit test, so raising it means restating both in the same commit. | `reports/r11-what-this-does-not-do.md` §4 |
| **D6** | **`kappa` 1/16 vs 1/12.** Knowingly 25% low; the stated geometry gives 1/12. | Frozen config, explicitly "the room decides". Both values pinned in tests so the choice stays visible. | `configs/thresholds.yaml:133` |
| **D7** | **CARLA groundwork — scope.** | **Zero existing work** in this repo or any sibling folder, and no scope has been supplied across two sessions. Starting a simulator integration from a guess is the wrong move; this needs a paragraph from you on intended scope. | `MORNING-SUMMARY.md` §3 |
| **D8** | **One agreed reference host + one agreed command for latency.** | Every latency disagreement in the project reduces to this. Not a measurement problem. **Now concrete:** since the vrgrid-26 merge the tree states *two* honest end-to-end figures — `README.md` 89.18/100.43 (Shrestha's host) and `handover:20` 108.65/127.23 (this host). Same quantity, different machines; one is 0.43 ms over budget and the other 27 ms over. Needs JP + Shrestha together. | `docs/handover-2026-09-02.md` latency note; `reports/latency-gap-investigation.md` |

---

## 2. [!] The one that blocks other work

**D1, the Patchwork++ singleton.** Flagging it separately because it is not just
another queue item — it is currently **distorting measurements other decisions
depend on**:

- `test_real_sequence_replay_is_identical` fails, correctly. Two replays in one
  process differ by 1,245 of 1,479,013 points.
- **~18% of the published seq-07 ring-1 RMSE is artifact**, not coarsening error
  (3.60 → **3.04 cm** once the reference and the map use a consistent ground
  mask).
- **No ring-1 accuracy comparison finer than ~0.5 cm can be adjudicated until it
  is fixed.** That is a live constraint on any future accuracy work, not a
  hypothetical.

Found twice independently — as the determinism gate failure, and as the ring-1
reproduction mismatch. The fix direction is measured, not speculative: two
estimators making one pass each agree exactly, 0 of 1.48 M points differing.

---

## 3. Ready to pick up — scoped, no decision needed

| # | item | notes |
|---|---|---|
| **R-a** | **Commit the measurement harnesses.** The recurring defect behind two unverifiable figures (see §5). Every `scratchpad/*.py` that produced a number in `reports/` should be in the repo. | Cheapest high-value item on the list. |
| **R-b** | **Locate the p99 cause.** p99 is 127–146 ms against a 100 ms budget and **no parameter, warm-up length, frame count or library version moved it.** p50 is within reach; p99's cause has never been isolated. | The real 10 Hz blocker. Nothing measured so far explains it. |
| **R-c** | **`stdout` UTF-8 at entry.** Deferred deliberately when the `⚑` crash was fixed at two call sites; the general fix would cover every script. | `pending-review/timing-table-unicode-crash.md` |
| **R-d** | **`ruff` E741 in `tests/test_metrics.py:472`** (ambiguous `l`). Pre-existing on `origin/main` from `014d388`, unrelated to any of this week's work, still red. | One-line fix, not my lane (tests/). |
| **R-e** | **README 99.87% vs `master-v4.md` 99.5%.** Logged as the same class of defect as the mIoU mismatch; never given its own pass. | Flagged in an earlier session, still open. |
| **R-f** | **Seq 00 ring-1 residual (0.32 cm).** Narrowed to a 61–89 scored-cell population difference; not closeable because the harness that produced the published number was never committed. Would close if R-a had been done earlier. | `reports/ring1-reproduction-investigation.md` §6 |

---

## 4. Closed this week — recorded so nobody re-raises them

| item | outcome | commit |
|---|---|---|
| `num_iter=2` latency tradeoff | **REJECTED on measurement.** Buys 5.42 ms, costs 19–54% of ring-0 RMSE concentrated on slopes. Curbs clean; slopes were the mechanism. | `c0ee403`, `860d58c` |
| The 80.78 / 97.72 ms latency claim | **RETIRED** across all seven files that carried it. Reproduces to 1.1% as a *synthetic* back-half benchmark; original run unrecoverable. | `5cddaa7` |
| 69.8% mIoU | **CORRECTED to 65.2%** in the four files that carried it, each now with its recipe. `research-log:402` determined **not** to be a defect. | `c632027`, `f3a0337` |
| `pypatchworkpp` unpinned | **PINNED to ==1.4.1** — also the fastest published wheel (18.58 ms vs 23.8–25.1 for every older release). | `23648e9` |
| `r9` self-contradiction | Withdrawn in place — the `--no-patchworkpp` inference was wrong. | `23648e9` |
| `VRGRID_DATA_ROOT` unset failing as "missing data" | **FIXED.** Names the cause and the fix. | `fac61c2` |
| Ring-1 reproduction mismatch (seq 07) | **ROOT-CAUSED** — the singleton. Seq 08 immune; seq 00 open (R-f). | `870766c` |
| Build provenance (native build vs wheel) | **Closed as a documented unknown** on your call — needs a multi-GB toolchain. | — |
| R11 limits page | **DONE.** | `e4bd731` |
| Ring 0 has no ρ (`known-limitations` §2b) | **FIXED 2026-09-17.** Within-cell variance in `spread`; ring 0 ρ 1.17 [1.13–1.29], n = 11 (after the §11 band fix). Roughness in the regret costmap keeps between-cell variance only. | — |
| §9.2 per-ring reference restricted to what each ring received (Aakash handover 2 Sep) | **DONE 2026-09-17.** `RingObservations`; `known-limitations` §9. | — |
| §2b eleven-sequence table stale | **REGENERATED 2026-09-17.** Ring 1 ρ 1.39 [1.22–1.53] (was 1.45 [1.26–1.59]); deck docs updated. | — |
| Money plot non-monotone step (Aakash handover 2 Sep) | **RESOLVED 2026-09-17** for seq 08 — paired over the same queries it is noise. Two real steps found elsewhere, see §5b. | — |
| `python -m vrgrid.dash` CPU-only; stale GPU note in `dashboard/gpu_stats.py` | **FIXED 2026-09-17.** `--device cuda`. | — |
| **D2 / R3** ring boundary under anisotropy | **FIXED 2026-09-17** (Shrestha, Aakash away). Ring membership decided per world-lattice block, coarse to fine; partition now CI-tested at adversarial speeds and headings. The defect was live at v = 0 on real seq 08 (nesting every frame, 0.224% of returns dropped); both 0 after. Snapping (part B) not used — see the status block in the file. | see `git log -- src/grid/lattice.py` |

---

## 5b. New open items, 2026-09-17 — found while closing Aakash's list

| # | item | notes |
|---|---|---|
| ~~**N-1**~~ | ~~Ring 3 on 08 / 09 / 10~~ **FIXED 2026-09-17.** Out-of-band heights were fused and re-basing hid saturation. 08 ρ 1.84 → 1.03. | `known-limitations` §11 |
| ~~**N-5**~~ | ~~Band floor ~2–3 m below road level~~ **REBALANCED 2026-09-17** to −3.5 / +4.5 m (still 8 m), chosen by survey of all eleven sequences. Seq 04 ring 3 24.5 → 18.2 cm; every ring 3 within 4% of its own returns. | `known-limitations` §11 |
| ~~**N-2**~~ | ~~Seq 07 uniform 20 cm regret spike~~ **FIXED 2026-09-17.** Footprint heights were count-weighted, which leaked neighbouring cells into planning cells; now area-weighted like the reference. Seq 07 monotone. | `known-limitations` §10 |
| **N-6** | Seq 09 uniform 40 cm < 20 cm regret (−0.084, 2.5 SE), unchanged by the N-2 fix. | Small; consistent with chance across 55 comparisons, but not explained. `known-limitations` §10. |
| **N-3** | **Seq 00 ring 2**: ρ 2.20 → 1.02 against its own returns. | Cross-look disagreement at 20–50 m, not coarsening. Cause open. `known-limitations` §9. |
| **N-4** | GitHub #6 ("dashboard/ has been removed") is stale since PR #7 brought Rerun back. | Shrestha's own issue; close it when convenient. |

---

## 5. The pattern worth acting on

Twice in two sessions a published figure turned out to be **unverifiable because
its harness was session scratch**:

- **p50 80.78 / p99 97.72 ms** — no log, no artifact, no script, no method in the
  commit.
- **Seq 00 ring-1 RMSE 6.77 cm** — differs by a 61–89 cell population difference
  from a re-measurement; `scratchpad/r1_accuracy_by_class.py` has never existed
  in the repository.

In both cases the number itself is probably fine. **The missing artifact is the
defect**, and in both cases it cost more time to investigate than committing the
script would have cost. That is item **R-a**, and it is the cheapest thing on
this list.

---

## 6. Housekeeping state

- **Branch:** `main`. **vrgrid-26 has been merged in** (see below); nothing
  pushed anywhere, per standing instruction.
- **`vrgrid-26`:** remote `vrgrid26` added and fetched on JP's explicit
  instruction, superseding the earlier "do not check" rule. `vrgrid26/main`
  merged into local `main` as a true merge (**not** a rebase — both sides had
  independent commits worth keeping, and rebasing would have rewritten
  already-pushed history). Shared base `5e0ebf3`, their 5 commits against our
  17. Four conflicts, all resolved by reading both sides. **Not pushed.**
- **`src/perception/frnet/`:** frozen, untouched.
- **`src/perception/ground.py`:** untouched — D1 is paused pending your design
  call, not attempted.
- **Gates:** `pytest` 672 passed / 1 failed (the determinism gate, D1) / 3
  skipped. `ruff` 1 error (R-d, pre-existing and unrelated).
- **`pending-review/` inventory:** 4 awaiting decision (D2, D3, D4 ×2), 4 now
  marked applied (`handover-latency-line-correction`, `r7b-mIoU`,
  `timing-table-unicode-crash`, and `patchworkpp-num-iter-tradeoff` as
  withdrawn-on-evidence). Two of those four had **stale "Applied? NO" headers**
  despite having been applied in `f3a0337`; corrected while assembling this list.
