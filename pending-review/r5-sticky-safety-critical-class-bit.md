# R5 — Sticky safety-critical class bit

**Status:** design only. **Nothing implemented.**
**Code it touches:** `src/grid/fusion.py` (Aakash) and `include/vrgrid/cell.py`
(**frozen — whole-team change**).
**Written:** 2026-09-12, against `main` @ `f3a0337`.

---

## 1. The defect

Class fusion is Boyer–Moore streaming majority packed into one byte
(`fusion.py:285`, `boyer_moore_update`):

```
counter == 0    -> candidate <- y,  counter <- 1
y == candidate  -> counter   <- min(counter + 1, COUNTER_MAX)
otherwise       -> counter   <- counter - 1
```

`semantic_class` is **5-bit candidate | 3-bit counter**, so `COUNTER_MAX = 7`.

A cell holds **one** class. A vulnerable road user whose returns are a minority
in a cell dominated by `road` (8) or `terrain` (16) returns is **voted away** —
the counter decrements on each road return until the VRU candidate is unseated,
and the cell reports `road`.

**This is the failure mode that matters most, and the geometry guarantees it.**
A distant VRU is *by definition* a small minority of returns in a road-dominated
cell: it subtends few beams, and the cell around it is road. The vote is
therefore most likely to erase a pedestrian exactly where the map has the least
other evidence about them — far away, early, while there is still time to act.

The file's own header already concedes the guarantee is weaker than textbook:

> `COUNTER_MAX + 1` contradicting observations unseat a genuine strict
> majority — `road` ×9 then `car` ×8 returns `car`.

For a VRU the relevant case is worse: the VRU never *had* the majority.

### Safety-critical classes

| class | learning id |
|---|---|
| person | **5** |
| bicyclist | **6** |
| motorcyclist | **7** |
| bicycle | 1 |
| motorcycle | 2 |

Ids 5/6/7 are the VRUs proper — a *person*, under whatever mode of transport.
1/2 are the unoccupied vehicles. **Which set the bit covers is a decision, not a
given** — see §6.

---

## 2. The fix

Add a **sticky bit in the flags byte** — *not* the class byte — set on **any**
observation of a safety-critical class, and cleared by **decay over N frames**
rather than by losing a vote.

This deliberately separates two different questions:

- `semantic_class` keeps answering **"what is this cell mostly?"** — unchanged,
  still Boyer–Moore, still one byte. Consumers that want the dominant surface
  (traversability's drivable-set test, the dashboard's class colouring) are
  untouched.
- the sticky bit answers **"has anything safety-critical ever been seen here
  recently?"** — a latch, not a vote.

A vote is the wrong instrument for the second question. Averaging out a rare
event is what a majority filter is *for*; the point here is that this particular
rare event must not be averaged out.

### Where the bit goes — there is room, and no struct growth

`include/vrgrid/cell.py:44` — the flags byte currently uses **four of eight
bits**:

```python
FLAG_DERIVED = 1 << 0   # value came from split(), not measurement
FLAG_REFINED = 1 << 1   # semantics forced a finer resolution than range alone
FLAG_BLIND   = 1 << 2   # inside the 3.74 m blind cone
FLAG_DYNAMIC = 1 << 3   # supplied by the transient layer this frame
```

**Bits 4–7 are free.** Proposed:

```python
FLAG_VRU_SEEN = 1 << 4  # a safety-critical class was observed here recently
```

**The 12-byte cell does not grow.** `CELL_BYTES = 12`, `CELL_FIELDS` unchanged,
`allocate()` unchanged, **every memory figure in the report is untouched** —
745,000 cells × 12 B = 8.94 MB, and the 21.5× / 286× ratios all hold. This is
the main reason to put it in `flags` rather than anywhere else.

⚑ **`include/vrgrid/` is the frozen interface directory.** CLAUDE.md: *"FROZEN
interfaces — whole-team change only, never edit unilaterally"*, and CODEOWNERS
routes it to all three devs. Adding one constant is a one-line diff and still
needs three-way sign-off. **Budget for that, don't assume it.**

---

## 3. Decay

The bit must clear, or a VRU who walked past thirty seconds ago haunts the cell
forever and the layer becomes noise.

### Use the clock that already exists

`frames_since_seen` (uint8, saturating) is already in the cell and is already
maintained — `fusion.py:265` resets it to 0 on observation, and the visibility
pass ages it. **No new field is needed.** Decay rule:

```
clear FLAG_VRU_SEEN where (flags & FLAG_VRU_SEEN) and frames_since_seen > N
```

### ⚑ But `frames_since_seen` answers a different question, and this is the design's weak point

`frames_since_seen` is *"frames since this **cell** was observed"*, not *"frames
since a **VRU** was observed in this cell."* A cell the vehicle keeps looking at
has `frames_since_seen == 0` forever, so the bit **never decays** there — which
is precisely the busy, near-field, road-dominated cell where a VRU is most
likely to have been a transient minority. **The failure mode is a permanently
latched bit on exactly the cells that matter most.**

Three ways out, in the order I'd consider them:

1. **Latch-and-count on the counter.** Reuse the 3-bit counter semantics: on a
   VRU observation set the bit *and* a small per-cell countdown; decrement per
   frame regardless of whether the cell was seen. Needs 3 bits of storage that
   `flags` has (bits 5–7) — still no struct growth, but it spends the whole
   remaining flag budget.
2. **Decay in the visibility pass**, where a cell is *tested* rather than
   *observed*. §10.4 already walks the occupied set per frame and already
   distinguishes "tested and cleared" from "not looked at". A bit aged there
   decays on a wall-clock-ish schedule rather than an observation one.
3. **Accept the latch and make it monotone-with-reset** — clear it only when
   the cell is cleared entirely (shift, or visibility cleanup). Simplest,
   weakest, and probably wrong for a rolling map.

**I have not chosen between these.** (1) is the most faithful to "decayed over N
frames"; (2) is the least storage; (3) is the least code. It is a real design
decision and it belongs to whoever owns `fusion.py`.

### Choosing N

N is a **threshold and therefore belongs in `configs/thresholds.yaml`**, which
is `frozen: true` — so it needs Shrestha's sign-off like the four keys already
queued. Do **not** hardcode it in `fusion.py`; CLAUDE.md is explicit that
thresholds live in configs and are frozen before schedules are compared.

Anchor for the value: at 10 Hz, N = 10 is one second, N = 30 is three. A VRU at
walking pace (1.4 m/s) leaves a 5 cm cell in ~36 ms and a 40 cm cell in ~290 ms,
so **N is not about how long they stay in the cell — it is about how long their
having been there should keep mattering.** That framing should drive the number.

---

## 4. What reads the bit

**Nothing, until someone wires it.** Setting a bit no consumer reads is a
no-op with a memory cost of zero and a review cost of three signatures, so the
change is only worth making alongside at least one reader. Candidates:

- **`traversability` / §7.1 bit 4.** A cell with `FLAG_VRU_SEEN` could be
  excluded from the drivable set regardless of its majority class. **This is a
  behaviour change to the planning surface** and would move plan-regret, the
  hazard-miss numbers in `reports/r7-hazard-miss-rate.md`, and the drivable-set
  accuracy in `reports/r1-accuracy-by-class-and-range-band.md`. Not a free add.
- **`confidence.drivable_confidence`.** Softer: the bit caps confidence rather
  than flipping the verdict. Fits the existing four-margin structure
  (`class_share`, `evidence`, `geometry`, `surface`) as a fifth gate, and
  `CHANNELS` already exists to name the binding one.
- **The dashboard.** Cheapest and safest: render it as an overlay beside the
  §7.4/§7.5 layers, read-only, no planning consequence. **Good first reader** —
  it makes the bit visible and verifiable before anything depends on it.

**Recommended order: set the bit → render it → only then let it affect a
verdict.** A safety bit that changes the planning surface on the same commit
that introduces it cannot be A/B'd against anything.

---

## 5. Test plan

1. **The motivating case, as a named test.** A cell receiving `person` ×1 then
   `road` ×9: assert `semantic_class` unpacks to `road` (**unchanged behaviour —
   the vote is not being altered**) *and* `FLAG_VRU_SEEN` is set. This is the
   test that would have caught the defect and it should read as such.
2. **Decay.** Same cell, advance N+1 frames without a VRU observation, assert
   the bit clears. Parametrise over the three decay designs if more than one
   survives review.
3. **The latch trap (§3).** A *continuously observed* cell that saw one VRU
   N+1 frames ago — assert the bit clears. **This is the test that fails for
   decay design (3) and probably (1).** Write it before choosing the design; it
   is the discriminator.
4. **Struct size is unchanged.** `assert CELL_BYTES == 12` and
   `np.dtype(CELL_FIELDS).itemsize == 12`. Cheap, and it is the invariant the
   whole "no struct growth" constraint rests on.
5. **No other flag disturbed.** Set/clear `FLAG_VRU_SEEN` and assert
   `FLAG_DERIVED|REFINED|BLIND|DYNAMIC` round-trip unchanged — a mask error
   here would silently corrupt the blind cone, which is *"unknown, never free"*
   and a hard invariant.
6. **Determinism.** The CI-blocking determinism test must still pass. A latch is
   order-independent (set-only within a frame), so it should — but assert it,
   because the bit is new state on the frame path.

---

## 6. Decisions for the owner — I have not made these

1. **Which classes.** Ids 5/6/7 (people) only, or also 1/2 (unoccupied bicycle
   and motorcycle)? A parked bicycle is not a VRU; a cyclist is. But class
   confusion between `bicycle` and `bicyclist` at range is exactly the kind of
   thing this bit exists to be robust to, which argues for including them.
2. **Which decay design** (§3) — the three options are genuinely different in
   cost and correctness.
3. **What N is, and where it lives** — `configs/thresholds.yaml` is frozen.
4. **Whether it affects traversability**, and if so on which commit. §4 argues
   for not on the first one.
5. **Whether one bit is enough.** One bit cannot say *which* safety-critical
   class was seen. Bits 5–7 are free, so 2–3 bits could distinguish
   person / rider / two-wheeler — at the cost of the whole remaining flag
   budget, with no way to get it back without growing the struct.
