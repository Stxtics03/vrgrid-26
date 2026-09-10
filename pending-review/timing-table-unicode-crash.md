# pending-review: `timing-table-unicode-crash.diff`

**File touched:** `scripts/timing_table.py` (2 lines)
**Found during:** task 1 (R9), while running `--alloc` to get per-stage memory
**Applied?** NO — modifies a tracked file, so per tonight's rules it waits for you.

## What it does

Replaces the `⚑` character with `[!]` in the **two `print()` calls** that
execute on the `--alloc` path (lines 459 and 464). Nothing else changes — the
four other `⚑` occurrences in the file (lines 9, 29, 60, 254) are in comments
and docstrings, are never encoded to the console, and are left alone.

## Why it needs fixing

`scripts/timing_table.py --alloc` **prints its whole table and then crashes**:

```
UnicodeEncodeError: 'charmap' codec can't encode character '⚑'
  timing_table.py:459 -> cp1252.py
```

The Windows console codepage is cp1252 and cannot encode `⚑`. Measured tonight:

| | exit code |
|---|---|
| `python scripts/timing_table.py --frames 20 --alloc` (as-is) | **1** |
| the same file with this diff applied | **0** |

The data is printed before the crash, so it is usable when a human is watching.
It is **not** usable from a Makefile, a CI step, or any `&&` chain — the script
reports failure on a successful run. Line 464 is a second, latent instance
behind `if wide and alloc.get("bin", 0) > 1e6`, so it only fires once `bin`
regresses past 1 MB/frame — i.e. exactly when you most want the diagnostic.

This is the same defect class I hit in my own dashboard code earlier in the
week and resolved the same way; `src/run/__main__.py` already prints `[!]` for
this reason.

## Why it is a decision and not an auto-apply

1. **It is not my file.** `scripts/timing_table.py` is Shrestha's. The house
   style uses `⚑` heavily and deliberately — this swaps it for ASCII in two
   places, which is a small style concession to Windows that the owner may
   prefer to solve differently.
2. **There is a competing fix.** Reconfiguring stdout to UTF-8 once at entry
   (`sys.stdout.reconfigure(encoding="utf-8")`) would keep `⚑` everywhere and
   fix every present and future instance in one line, rather than patching
   call sites as they are found. I did not choose between them — that is a
   maintainer's call, and it affects every other script in `scripts/` that
   prints `⚑` too.
3. **The blast radius is unmeasured.** I only checked `timing_table.py`. Other
   scripts almost certainly have the same latent crash; a per-site fix leaves
   them broken, an stdout fix would need applying repo-wide.

## To apply

```bash
git apply pending-review/timing-table-unicode-crash.diff
python scripts/timing_table.py --frames 20 --alloc; echo $?   # expect 0
```
