# vrgrid-26 — repo setup runbook

*Shrestha, 2026-09-05. Old: `github.com/Stxtics03/vrgrid` · New:
`github.com/Stxtics03/vrgrid-26`*

---

## The one decision to make first: history, or fresh start?

**Preserve the history. Mirror it.**

The old repo is **206 commits** with an append-only research log, dated
correction notes, and a `known-limitations.md` that root-causes every defect the
project hit. That record is not overhead — it is the single best piece of
evidence that this was engineered rather than assembled.

For scale: the competing team's grid engine has **13 commits**, and the
competitor review's §2 closing note says their two evaluations disagreed sharply
*because* they had no shared process record. Your log is the thing that stops
the same outcome, and starting a clean repo throws it away for nothing.

⚠️ A fresh `git init` and one "initial commit" of the current tree would make a
three-week project look like a weekend one. Don't.

---

## 1. Create the empty repo

On GitHub, create `Stxtics03/vrgrid-26`. **Do not initialise it** — no README, no
`.gitignore`, no licence. The mirror push needs it empty or the push is rejected.

Visibility: **public**, same as the old one. The deck cites the repo link, and a
private repo behind a login is worse than no link.

---

## 2. Mirror the history across

```bash
# somewhere temporary, not your working checkout
git clone --mirror https://github.com/Stxtics03/vrgrid.git vrgrid-mirror
cd vrgrid-mirror
git remote set-url --push origin https://github.com/Stxtics03/vrgrid-26.git
git push --mirror
cd .. && rm -rf vrgrid-mirror
```

`--mirror` carries every branch, every tag and all 206 commits. Two minutes.

**Verify before anyone starts work on it:**

```bash
git clone https://github.com/Stxtics03/vrgrid-26.git && cd vrgrid-26
git rev-list --count HEAD        # must print 206
git log -1 --format="%H %ad"     # must match 8882ec3, 2026-09-04
```

If the count is wrong, stop and re-mirror. Everyone cloning a broken base is a
bad afternoon.

---

## 3. Point your working checkout at the new remote

Each person, once:

```bash
cd vrgrid
git remote set-url origin https://github.com/Stxtics03/vrgrid-26.git
git remote -v                     # confirm both fetch and push moved
```

⚠️ **Tell the team the moment this is done.** JP has tonight's `ground.py` work
sitting local and uncommitted. Until he knows the remote exists, he has nowhere
to put it — and un-pushed work on one laptop is exactly how this team loses a
day.

---

## 4. Archive the old repo, don't delete it

On `Stxtics03/vrgrid` → Settings → Archive this repository.

Archiving makes it read-only and removes the risk of someone pushing to the dead
remote for three days without noticing. **Do not delete it** — the SIH
submission, the deck and every document currently cite that URL.

Add one line to the old README before archiving:

> **This repository is archived.** Development continues at
> `github.com/Stxtics03/vrgrid-26`.

---

## 5. What to add on top

Everything already in the mirror, plus the new documents:

```
docs/presentation/      00–10, the deck/script audit and corrected material
docs/gpu-lane/          00–04, the Shrestha/Pratyushi cycle plan
docs/data-access/       DRDO and IIIT-H request specs
```

⚠️ **`docs/presentation/` is round-one material and some of it is now stale.**
The corrected script, the CUDA/deck audit and the panel Q&A are still live and
still needed. But anything quoting ρ ≈ 1.45 at ring 1 is **provisional until
JP's ground.py bug is resolved** — see §7.

Put a header on `docs/presentation/00-START-HERE.md` saying so, rather than
deleting anything. This project's failure mode is corrections landing in one
place and not the others; a stale doc that says it's stale is safe.

---

## 6. Set it up so the cycle's rules are enforced, not remembered

Three things, fifteen minutes, and they prevent the two failure modes the
competitor review calls out.

**a) Branch protection on `main`.** Settings → Branches → add rule:
- Require a pull request before merging
- Require status checks to pass (`make test`, `ruff`)
- **Do not** require approvals — six people on a ten-day cycle, that's friction

**b) Confirm CI came across.** The mirror carries `.github/workflows/`, but the
Actions tab needs enabling on a new repo. Push a trivial commit and confirm a
run starts. ⚠️ **Expect the determinism job to be red** — see §7.

**c) `CODEOWNERS`.** This is the cheap version of the directory-ownership model,
and it makes R3/R4's cross-boundary handoff visible automatically:

```
/src/grid/          @aakash
/src/eval/          @aakash
/src/gpu/           @Stxtics03
/src/perception/    @jp
/dashboard/         @jp
/docs/research-log.md
```

Leave the research log with no owner — everyone writes to it, nobody gates it.

---

## 7. ⚠️ Do this before anyone trusts a number in the new repo

JP has diagnosed a real bug in `src/perception/ground.py`: the Patchwork++
estimator is a module-level singleton (`_estimator = None`, line 89), built once
and reused across every frame. Patchwork++ carries internal state between calls,
so **the same scan fed twice does not produce the same answer.**

He reports it explains a failing determinism test and roughly 18% of inflation in
a published ring-1 accuracy number.

**Three things have to be pinned down before the new repo's docs are trusted:**

1. **Which determinism test is failing.** `tests/test_determinism.py` *injects*
   `is_ground` as a boolean array (line 28; lines 147–148) and never calls
   `segment_ground()`. So the scatter/fuse/hash determinism claim does not
   involve Patchwork++ at all. The only test that could is
   `test_real_sequence_replay_is_identical` (line 203). **Kernel determinism
   intact but end-to-end broken** is a very different statement from *"our
   determinism claim is false"* — and the deck makes the broad version.

2. **Which direction the 18% moves ρ.** Lower ρ is better. If the reported
   1.45 is inflated, the true value is nearer 1.23 and the result is *stronger*.
   Nobody should touch a slide until that sign is established.

3. **Whether it touches the eleven-sequence table**, `known-limitations.md` §2b,
   or only ring 1 on some sequences.

**Open a tracking issue on `vrgrid-26` on day one** and link every affected
document to it. This project's recurring failure is a correction landing in one
file and not the other six — 69.8% mIoU is still in eight places for exactly that
reason. An issue is the cheap fix.

---

## 8. Also pin the Patchwork++ build

`1c7c24d` records `git clone --depth 1` of `url-kaist/patchwork-plusplus` — which
is **untagged HEAD as of 2 September**, with no commit pin and no OS or toolchain
recorded. Two people cloning on different days get different C++ code, and
nothing in the repo would show it.

Fix it in the new repo:

```bash
# capture what you actually built against
cd patchwork-plusplus && git rev-parse HEAD
```

Then record in `pyproject.toml` or `docs/`:

```
patchwork-plusplus @ <full-sha>
built on: <distro + version>, gcc <version>, cmake <version>
```

⚠️ **This is directly load-bearing for JP's investigation.** He is trying to
explain a 12.41 ms vs 20–21 ms ground-segmentation gap between your machines. If
the two of you built different commits, that is a candidate cause — and right
now neither of you can tell, because nothing was recorded.

---

## 9. Checklist

- [ ] `vrgrid-26` created, empty, public
- [ ] `git push --mirror` done
- [ ] `git rev-list --count HEAD` prints **206** on a fresh clone
- [ ] **Team told the remote is live** — JP is blocked on this tonight
- [ ] Everyone's `origin` re-pointed
- [ ] Old repo archived with a pointer line in its README
- [ ] `docs/presentation/`, `docs/gpu-lane/`, `docs/data-access/` added
- [ ] Provisional-numbers header on `00-START-HERE.md`
- [ ] Branch protection + status checks on `main`
- [ ] CI runs; determinism job status recorded (red is expected)
- [ ] `CODEOWNERS` committed
- [ ] Issue open for the ground.py singleton, all affected docs linked
- [ ] Patchwork++ commit SHA and toolchain recorded
