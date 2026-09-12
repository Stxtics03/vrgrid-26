# Patchwork++ build record — Shrestha's machine

Closes the last item of `VRGRID-26-SETUP.md` §8 and its checklist line
("Patchwork++ commit SHA and toolchain recorded").

Recorded 2026-09-12. Everything under **Measured** was read off the installed
artefact on this machine. Everything under **Reconstructed** is inference with
its evidence attached — read the distinction before quoting any of it.

## Measured

| Field | Value |
| --- | --- |
| Package | `pypatchworkpp` **1.4.1** |
| Built | **2026-09-02 13:57 +0530** (mtime of the extension module) |
| Extension | `pypatchworkpp.cpython-314-x86_64-linux-gnu.so` |
| ELF build-id | `2e868d4a3cc511362b5b8393902657e408bfd7c3` |
| sha256 of `.so` | `2fa0ce097050682b4a6f0d12ece0e91f37f7bb0b74eb9ed46926fa8f128c86d4` |
| Compiler | **GCC (Debian 15.3.0-2) 15.3.0** — read from the binary's `.comment` section, so this is what actually compiled it |
| Build backend | scikit-build-core 1.0.3, wheel tag `cp314-cp314-linux_x86_64` |
| OS | Kali GNU/Linux Rolling, `VERSION_ID=2026.3` |
| Kernel | `7.1.5+kali-amd64` (Kali 7.1.5-1kali1, 2026-07-29) |
| glibc | Debian GLIBC 2.42-17 |
| Python | 3.14.6 (venv at `.venv/`) |

## Reconstructed

**Upstream commit: `3e6903a1d5537a4cc2ace897b0bbb98a92d6014c`** — `url-kaist/patchwork-plusplus`,
tag `v1.4.1`, committed 2026-05-23T06:45:16Z.

Not read from a local checkout — see *Not recoverable* below. The evidence:

- Commit `1c7c24d` in this repo records the install as `git clone --depth 1` of
  upstream, performed on 2 September; the binary's mtime (2026-09-02 13:57)
  agrees.
- Upstream's default branch is `master`. It has been at `3e6903a` since
  2026-05-23 and is still there as of 2026-09-12: **zero commits landed in that
  window** (GitHub commits API, `since=2026-05-23T06:45:17Z&until=2026-09-02`,
  returns 0).
- `3e6903a` is tagged `v1.4.1`, and the installed package reports version
  `1.4.1`. Version and date both agree.

A `--depth 1` clone on any day between 23 May 2026 and now therefore lands on
the same commit. Confidence is high, but this is still reconstruction: nobody
ran `git rev-parse` at build time.

### Consequence for the ground-segmentation timing gap

`VRGRID-26-SETUP.md` §8 flags "two people cloning on different days get
different C++ code" as a candidate cause of the **12.41 ms vs 20–21 ms**
ground-segmentation gap under investigation.

For this window that risk did not materialise — upstream was static for over
three months, so any `--depth 1` clone in that period produced identical C++.
**Different Patchwork++ source is effectively ruled out**, provided JP also
cloned between 23 May and today. That leaves the toolchain and the machine as
the live candidates, and GCC 15.3.0 on Kali rolling is unusual enough to be
worth comparing first.

This does not touch the `ground.py` stateful-singleton defect (issue #1), which
is a separate and still-open problem.

## Not recoverable

- **The source tree.** `direct_url.json` records the build input as
  `file:///tmp/claude-1000/-home-shrestha-Desktop-sih26/61b3d0c4-.../scratchpad/patchwork-plusplus/python`
  — a session-scoped scratchpad under `/tmp`, since deleted. The checkout that
  produced this binary no longer exists, so `git rev-parse HEAD` has no target.
- **The cmake version.** `cmake` is not on this machine's PATH today, so
  scikit-build-core almost certainly provisioned one into an isolated build
  environment, which was discarded with the build. The setup doc asks for a
  cmake version; it cannot be supplied honestly for this build. Future builds
  should record it at build time.

## For JP — comparing the two machines

The build-id is a stronger comparator than a git SHA here, because it also
catches a toolchain difference. Run this on the other machine and compare all
four lines:

```bash
SO=$(python -c "import pypatchworkpp; print(pypatchworkpp.__file__)")
python -c "import importlib.metadata as m; print('version:', m.version('pypatchworkpp'))"
readelf -n  "$SO" | grep -A1 'Build ID'
readelf -p .comment "$SO"
sha256sum   "$SO"
```

Matching build-ids mean identical code and identical toolchain, and the timing
gap is then a machine or configuration difference, not a build difference.

## Pinning it from here

```bash
git clone https://github.com/url-kaist/patchwork-plusplus.git
cd patchwork-plusplus && git checkout 3e6903a1d5537a4cc2ace897b0bbb98a92d6014c
pip install ./python
```

Use the explicit checkout rather than `--depth 1`. Upstream being static is
luck, not a guarantee, and it is exactly what §8 warned about.
