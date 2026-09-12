# The deep learning model — what you would have said, and what to say instead

*Same format as `09`. **Part A** is the deck and the script. **Part B** is the
live demo.*

**The situation here is the opposite of the GPU one.** With GPU you claimed work
you hadn't done. With deep learning you did substantial work and **claimed none
of it.** Across six slides, FRNet is never mentioned. Your only statement on the
subject is *"Nothing is trained"* — which is true of the shipped pipeline, and
which currently reads as an absence rather than a decision.

Under a **Smart Vehicles / Software** theme, *"where's the AI?"* is a likely
question, and right now it has no good answer.

---

## What you actually have

| | |
|---|---|
| Ported FRNet from ~15% to | **90.3% point accuracy, 65.2% mIoU** on 200 held-out frames of seq 08 (paper: 73.3%) |
| Found three divergences | wrong activation ×7 sites · a config overriding the trained projection FOV · a densification transform needing verbatim reproduction *including its off-by-one* |
| Found the forward pass was | **10.5 s/frame**, ~90% inside a Python loop |
| Fixed it with | `torch.scatter_reduce_` — **1408× on max, 541× on mean** at real shapes on CUDA |
| Which took | a fine-tune from **3.3 h to 2.2 min** |
| Fine-tuned it | **three ways, rejected all three on measurement** |
| And then | **deliberately kept it out of the pipeline** |

That last row is the one that lands. It reframes "nothing is trained" from a
limitation into experimental discipline.

⚠️ **65.2%, never 69.8%.** The 69.8 figure is an arithmetic error still live in
eight places. See ③.

---

# PART A — the deck and the script

## ① "Nothing is trained"

> 🗣️ **You would have said:**
> *"Nothing is trained. Classes and motion flags come straight from the dataset's
> label files."*

**⚠️ True, but it stops one sentence too early** — and it leaves you with nothing
to say when someone asks about machine learning.

**→ Say instead:**

> *"Nothing is trained for the shipped pipeline — semantic classes and the
> moving-object flags come straight from the raw label files. And that's a
> deliberate choice rather than a shortcut: it means our mapping result is
> evaluated independently of segmentation quality. A bad coarsening ratio can't
> be blamed on a mis-segmented kerb, and a good one can't be credited to a strong
> segmenter. We did build the model — I'll come to it."*

*The last clause is what buys you ②. Without it, "nothing is trained" closes the
topic and you never get to say the good part.*

---

## ② "Where is the machine learning in this?"

> 🗣️ **You would have said:**
> *…nothing prepared. Probably some version of "we don't use any — it's all
> ground truth labels,"* which sounds like you didn't do the work.

**→ This is your answer. It's the strongest unused material in the project:**

> *"We built one and then chose not to put it in the pipeline, and the choice is
> the interesting part.*
>
> *We ported FRNet — a frustum-range segmentation network — and it initially
> scored about fifteen percent point accuracy. The network loaded, it ran, and it
> produced nonsense. We found three causes. The wrong activation function at seven
> sites in the backbone: the checkpoint trained with mmcv's HSwish and the port
> had LeakyReLU. A config that was overriding the model's trained projection with
> the sensor's physical field of view — those are different quantities, because
> the checkpoint learned a fixed spherical projection. And a densification
> transform we had to reproduce verbatim, including an off-by-one we kept
> deliberately, because the paper's published number was measured with it and
> fixing it would make our result incomparable.*
>
> *It now scores 90.3 percent point accuracy and 65.2 mIoU on 200 held-out frames
> of sequence 08, against the paper's 73.3.*
>
> *And we keep it out of the mapping pipeline on purpose, so segmentation error
> can't contaminate the mapping result. We report it alongside the map, never
> swapped into it."*

*Roughly 50 seconds. Have it ready as a backup slide, or fold the first and last
paragraphs into slide 4.*

---

## ③ The mIoU number

> 🗣️ **You would have said:**
> *"69.8 mIoU against the paper's 73.3."*

**❌ Arithmetic error.** The 15 per-class IoUs sum to **977.7**. Divided by 15
that's 65.18%. Divided by 14 it's 69.84%. The missing class is `other-ground` —
150 ground-truth points across the run, IoU 0.0%, **present in the data and
therefore counted**. Point accuracy reproduces exactly at 90.3%, so this is
arithmetic, not a model or data difference.

**Still live in eight places:**

```
docs/handover-2026-09-02.md:23, :169     docs/demo-runbook.md:229
docs/perception-dashboard-summary.md:150 src/perception/CLAUDE.md:9
src/perception/semantics.py:14           scripts/frnet_fast_scatter.py:33, :159
```

**→ Say instead:**

> *"65.2 mIoU, over the fifteen classes present in those frames, against the
> paper's 73.3."*

**And if someone has seen 69.8 in an older doc:**

> *"That was our arithmetic error — we divided by fourteen, dropping
> other-ground, which has 150 ground-truth points across the run and an IoU of
> zero. It's present in the data so it counts. We caught it in our own audit and
> corrected downward. Point accuracy is unaffected at 90.3."*

*Volunteering a self-caught error that moved a number **down** is worth more than
the 4.6 points it costs you.*

---

## ④ The point-accuracy number

> 🗣️ **You would have said:**
> *"98.3 percent point accuracy."*

**❌ That's one frame** — sequence 00, frame 43, from the port-validation work.
The reported figure is **90.3%** over 200 frames of sequence 08.

Both are in the repo unqualified (`perception/CLAUDE.md:9`, `semantics.py:14`,
`handover:169`), so it's an easy slip.

**→ Say 90.3% only.** If 98.3 comes up: *"that's a single-frame port check, not
the result."*

---

## ⑤ "Your own repo says the port is non-functional"

> 🗣️ **You would have said:**
> *"FRNet didn't work, so we used ground truth labels instead."*

**❌ This is the version that costs you the most**, because "we tried a deep
learning model and it failed" and "we ported one to 90.3% and then chose not to
use it" are completely different stories — and only the second one is true.

**Six documents plus the code still say non-functional:**

```
CLAUDE.md:66                     data/README.md:29
docs/team-assignments.md:110     docs/known-limitations.md:807
docs/execution-plan.md:37, :233  docs/master-v4.md:280
src/perception/semantics.py:295  ← "Disabled -- the standalone port is non-functional"
```

That last one is *in code a judge can open.*

**→ Fix the docs, and if asked:**

> *"Those are stale — flagged in our own audit and not yet cleaned up. The port
> was non-functional at about fifteen percent until the second of September; it
> works now at 90.3. The reason it isn't the map's semantic source changed from a
> defect into a design choice, and some of the docs still carry the old reason."*

---

## ⑥ "Why isn't the model in your pipeline?"

> 🗣️ **You would have said:**
> *…under the old framing, "because it doesn't work."*

**→ Say instead:**

> *"Because using ground-truth labels isolates what we're actually claiming. The
> contribution is the variable-resolution grid, not the segmentation. If we ran
> our own segmenter, every accuracy number would be a joint measurement of the map
> and the model, and a reviewer couldn't tell which one produced the result. With
> ground-truth labels, our coarsening ratio measures coarsening.*
>
> *The model is reported alongside, so you can see both, and swapping it in is a
> config change rather than an architecture change."*

---

## ⑦ Fine-tuning

> 🗣️ **You would have said:**
> *…nothing. It isn't mentioned anywhere in the deck or script.*

**→ Worth one slide or one answer, because a documented negative result is a
stronger position than never having tried:**

> *"We fine-tuned it three ways and rejected all three on measurement. Head-only
> with three-times class weights on the classes our map consults: mIoU went from
> 65.2 down to 64.6. Head-only without class weights at a lower learning rate:
> 65.3, which is inside noise. Head plus backbone for four thousand steps: 64.5.*
>
> *That's the expected answer rather than a failure to tune. The checkpoint was
> already trained on sequences 00 through 10 excluding 08, so every recipe was
> retraining on its own training set with no domain gap to close.*
>
> *Two things we learned doing it. Training loss fell across the run that scored
> worst — which is exactly why training loss isn't a result: a class-weighted loss
> falls when the head gets more confident on the weighted classes, whether or not
> it gets more correct. And freezing weights isn't freezing a module — model.train()
> puts BatchNorm into training mode, so a frozen backbone still drifts its running
> statistics on every forward pass. The weights hold still and the function the
> module computes doesn't."*

*Those last two sentences are the kind of thing that makes an ML-literate judge
sit up. Very few hackathon teams know the BatchNorm one.*

---

## ⑧ "Your model is worse than the published number"

> 🗣️ **You would have said:**
> *…probably defended it, or apologised.*

**→ Neither. Explain what the gap is made of:**

> *"Yes — 65.2 against 73.3. Part of that is real and part is measurement: we
> evaluate on 200 frames of sequence 08 rather than the full validation set, and
> our fifteen-class mean includes other-ground at zero IoU, which has 150 points
> in the whole run. We didn't drop it, because it's present in the data.*
>
> *We also didn't chase the gap, because closing it wouldn't change any claim we
> make — the model isn't in the pipeline. What we did chase was the port
> correctness, from fifteen percent to ninety, and the numerics of the reduction
> kernel we replaced."*

---

## ⑨ "Isn't using ground-truth labels cheating?"

> 🗣️ **You would have said:**
> *"They're just the dataset's labels."* — true but defensive.

**→ Say instead:**

> *"It would be if the labels were the contribution. They're the control. We're
> claiming something about a map representation, so we hold the perception input
> fixed and vary only the thing we're testing. The alternative — running our own
> segmenter — would mean every number is a joint measurement of the map and the
> model, and you couldn't attribute the result to either.*
>
> *We disclose it in the deck, in the README and in the module docstring. And the
> model exists, so anyone can measure the joint version."*

---

## ⑩ The reduction speedup — this is also DL work, not just GPU work

> 🗣️ **You would have said:**
> *…nothing.*

**→ Frame it as engineering on the model, because that's what it is:**

> *"We also found the forward pass was ten and a half seconds a frame, with about
> ninety percent of that inside a Python loop — scatter_max and scatter_mean were
> iterating once per output slot, twenty-five thousand iterations over a
> hundred-and-twenty-four-thousand-row tensor, seven times per forward. We
> replaced them with torch.scatter_reduce: 1408 times faster on max, 541 on mean,
> at real shapes on CUDA. A fine-tune went from three and a quarter hours to two
> minutes.*
>
> *And we verified the numerics rather than assuming them. Max is bit-identical
> on CPU and CUDA. Mean differs by up to two float32 ulp on about forty percent
> of slots on CUDA, because the native kernel sums a slot's rows in a different
> order and float addition isn't associative — so our verifier gates max at
> exactly zero and mean at a stated ulp bound, rather than claiming a
> bit-identity that isn't there."*

*Overlaps with `09` ⑧ — use it in whichever context the question arrives.*

---

## ⑪ "Did you train anything at all?"

> 🗣️ **You would have said:**
> *"No, nothing is trained."*

**⚠️ Careful — you ran three fine-tuning jobs.** "Nothing is trained" is true of
the shipped pipeline and false of the project. Don't get caught on the
distinction.

**→ Say instead:**

> *"Nothing that ships. We ran three fine-tuning experiments on the segmentation
> model and rejected all three on measurement, so the pretrained checkpoint is
> what we report — and the map itself takes its labels from ground truth
> regardless."*

---

# PART B — during the live demo

*Five moments. The recurring trap here is the inverse of the GPU one: **the
dashboard looks exactly like the output of a segmentation network.** Coloured
semantic points, moving objects flagged in a different colour, per-cell
confidence. A judge watching that will reasonably assume you're running
inference — and you've just told them nothing is trained.*

---

## ⑫ Any scene with semantic colours on screen

> 🗣️ **You would have said:**
> *"You can see the semantic classes here — road, vegetation, buildings."*

**❌ It looks like model output.** If you've said "nothing is trained" and then
show coloured segmentation, one of those two things has to be explained, and
better by you.

**→ Add, the first time colours appear:**

> *"Those semantic colours are ground-truth labels from the dataset, not
> inference — that's deliberate, so our mapping result isn't entangled with
> segmentation quality. We do have a segmentation model and I can show you its
> numbers, but it isn't in this loop."*

---

## ⑬ The ghost scene — moving objects highlighted

> 🗣️ **You would have said:**
> *"The system identifies moving vehicles and clears their trails."*

**❌ "Identifies" implies detection.** It doesn't detect motion — it reads the
four `moving-*` raw label ids (252 car, 253 bicyclist, 254 person, 255
motorcyclist) from the label file.

**→ Say instead:**

> *"Motion flags come from the label files too — the four moving-star classes.
> What our system does is decide what to do about them: the transient layer, and
> a visibility check that clears cells the current scan can see through, with a
> guard that never clears a cell holding a return in the current scan."*

*The distinction matters: your contribution is the **removal**, not the
**detection**, and claiming detection invites a question about a MOS model you
don't run.*

---

## ⑭ The features scene — per-cell confidence

> 🗣️ **You would have said:**
> *"And here's per-cell confidence."*

**❌ Two traps at once.** It looks like model confidence, and it isn't calibrated.

**→ Say instead:**

> *"Per-cell confidence — four derived channels combined by taking the weakest,
> and nothing stored, so the cell stays twelve bytes. Two caveats we'd rather say
> than be asked: it's a margin, not a probability — nothing has been fitted
> against outcomes, so 0.6 isn't a sixty percent chance of anything. And the
> label channel is a floor rather than an estimate, because our class counter
> saturates at seven: a cell observed 200 times unanimously reports a lower share
> than one observed eight times."*

---

## ⑮ "Can you show the model running?"

> 🗣️ **You would have said:**
> *…nothing prepared, and possibly "it's not set up."*

**→ You can actually do this, and it's about a minute:**

```bash
python scripts/frnet_eval.py --frames 200 --fast-scatter
```

> *"Yes — this is the port on 200 held-out frames of sequence 08, and it's the
> one thing in the project that genuinely loads the GPU. Without the
> fast-scatter shim this run takes about thirty-five minutes; with it, about
> one."*

⚠️ Needs `VRGRID_FRNET_CHECKPOINT` set to the `.pth` path. **Verify tonight** —
if the checkpoint isn't on the presenting machine, don't offer this.

---

## ⑯ "Why is your inference ten seconds a frame?" — if someone reads `frnet/`

> 🗣️ **You would have said:**
> *…this is a real risk, because the frozen port genuinely contains those loops.*

**→ Say instead:**

> *"It isn't, behind the fast-scatter flag. We shim the reductions at runtime
> rather than editing the port, because the port is frozen deliberately as a
> reference — so the numbers we report can't move underneath us. The loops you're
> looking at are the upstream implementation, and the shim replaces them at
> import with native scatter_reduce."*

---

## Numbers to have ready

| | |
|---|---|
| **90.3%** | point accuracy, 200 frames seq 08 |
| **65.2%** | mIoU, 15 classes present — **never 69.8** |
| **73.3%** | the paper's number |
| **~15% → 90.3%** | what fixing three divergences bought |
| **1408× / 541×** | scatter_reduce on max / mean, CUDA |
| **3.3 h → 2.2 min** | fine-tune wall time |
| **3 recipes, all rejected** | 64.6 / 65.3 / 64.5 against 65.2 |
| **00–10 minus 08** | what the checkpoint trained on — so 08 is a real hold-out |

*That last row is worth knowing: the segmentation model is the **one place in
this project where a genuine hold-out exists.** Everywhere else, 07 and 08 were
simply the sequences that downloaded first.*

---

## Checklist

**Tonight — JP's files, since a judge can open them:**
- [ ] `src/perception/CLAUDE.md:9` — 69.8 → 65.2, qualify 98.3 as single-frame
- [ ] `src/perception/semantics.py:14` — same
- [ ] `src/perception/semantics.py:295` — "non-functional" → disabled by design
- [ ] The six docs listed in ⑤

**Deck:**
- [ ] Slide 4 — extend "Nothing is trained" per ①
- [ ] Add the FRNet block to slide 3 or 4, or as a backup slide (②)

**Demo — rehearse two:**
- [ ] ⑫ the first time semantic colours appear
- [ ] ⑬ "motion flags come from the labels; the removal is ours"
- [ ] Verify `VRGRID_FRNET_CHECKPOINT` before offering ⑮
