# Implement — the sweep resolves the branch it used to believe

One pull request. `bin/sd_sweep.py` +59, `bin/sd_lib.py` and `bin/sd_skill.py`
net zero, `tests/test_sd_sweep.py` +228 against −13.

| unit | lines |
|---|---|
| `branches()`, the one query per root | 26 |
| the annotation on the row, and `LIVE`/`GONE`/`UNKNOWN` | 15 |
| `sweep()` calling it, `render()` printing it | 11 |
| the module docstring paragraph | 7 |

`bin/` stands at 17,182 against `BIN_CAP` 17,250 — 68 lines of headroom, from
127 before. No cap moved, and the cap-raise rule was never reached.

## What changed

**The exclusion at `bin/sd_sweep.py:91` is gone.** `if item.status !=
SWEEPABLE_STATUS or item.branch` lost its second clause. Every non-archived,
non-parked `planning` item past the threshold is now in `due` whatever its
`branch:` field says.

**`branches(root)` asks git twice and returns a `frozenset[str] | None`.**
`for-each-ref refs/heads` for local heads, `ls-remote --heads <remote>` with no
branch argument for published ones, unioned. `None` is git's failure, which
`sd_lib.git_output` already reports for both a non-zero exit and a root that is
not a checkout.

**`scan()` takes the answer rather than fetching it**, defaulting to `None`.
That is the seam criteria 3 and 4 are tested through: a per-root answer can be
varied per root, and "git could not say" is reachable without breaking a git.

**`sd_lib._upstream` is now `sd_lib.upstream`.** It had one cross-module reader
carrying `# noqa: SLF001 - the one reader of this fact`, and this change would
have made that comment false and added a second `noqa`. The underscore goes,
its three sites follow, and the `noqa` and its comment go with them.

**`bin/sd` is untouched.** The `sweep` verb already hands `sd_sweep.sweep` a
list of `(where, root)` pairs, which is exactly the per-root seam this needed,
and `--json` carries the new fields without being told about them.

## The render

```
pack  (3 active)
    99d  alpha  (feat/x gone)
    70d  beta  (feat/y live)
    60d  gamma
```

An item with no `branch:` field prints as it did. The annotation is visible
rather than ambient, which is what makes `gone` mean something when it appears.

A root whose git refused prints one line under its own heading —
`git could not list this repository's branches` — and every annotation beneath
it reads `unknown` for that one reason.

## Scores

| criterion | evidence |
|---|---|
| 1 — a deleted branch is annotated gone and the item is due | `test_a_deleted_branch_is_annotated_gone_and_the_item_is_due` |
| 2 — a live branch is annotated live, the listing unchanged | three tests: local, remote-only, and no field at all |
| 3 — resolution is per-root, asserted not assumed | two tests: one on `scan`, one on `sweep`, the second added because the first could not catch the fixed-root mutation |
| 4 — "git cannot answer" is distinct, once per root | three tests: a non-checkout root, a failing `ls-remote`, and the one-line render |
| 5 — one query per root, both sources, count unchanged | `test_one_remote_query_per_root_classifies_two_remote_only_branches` asserts one `ls-remote` in the recorder's log and that its argv does not name a branch; `test_the_item_count_is_the_same_across_all_three_annotations` builds the same item three times |
| 6 — mutation-tested | below |

**The mutation run, and the gap it found.**

| mutation | result |
|---|---|
| `live` and `gone` swapped | 6 failures |
| the per-root argument replaced by a fixed root | 1 failure |
| "git cannot answer" made to report `gone` | 1 failure |

The middle row did not fail on the first run. Criterion 3's test called
`scan()` directly and passed the two answers in itself, so it proved the
annotation and never the resolution — `sweep()` is the only caller that decides
*which* root to ask, and a `sweep()` asking the first root about everything
passed the whole suite. `test_sweep_resolves_each_root_against_itself` is that
test, and the mutation dies on it. This is the case criterion 6 exists to find
and it found one.

## The code review, and the one finding it made

One pass, per the Development / code row. Copilot recommended approval and
raised one issue: the `branches()` docstring was inaccurate about subprocess
counts. Verified before acting on it — a recording `git` on `PATH` shows
**seven** invocations per root, not the two the docstring implied:

```
for-each-ref --format=%(refname:short) refs/heads
remote
rev-parse --abbrev-ref HEAD
config --get branch.main.remote
symbolic-ref --short refs/remotes/origin/HEAD
rev-parse --verify --quiet main
ls-remote --heads origin
```

Five of the seven are `sd_lib.upstream` resolving which remote to ask, and they
are local reads; exactly one leaves the machine. The docstring and `design.md`'s
D5 and Risks section now say seven and name the one that is a round trip. The
claim the cost argument actually rests on — per root, never per item — was
right and is unchanged.

## Gates

`make lint`, `make test`, `make check` each exit 0. 28 tests in
`tests/test_sd_sweep.py`, up from 18: one deleted, eleven added.

The suite-shape rule caught the new class appended below the runner block
(`tests/test_suite_shape.py:67`); the runner block moved to the end of the file.
