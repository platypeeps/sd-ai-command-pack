# Implementation plan — split the planning contract, stop shipping the Codex lane

> **Executed, then re-cut at the test gate.** Steps 1 through 6 below were run
> as written for the PRD's option 5 and completed green in isolation; `make
> test` then refused the manifest row through three tested invariants
> (`design.md` D6), and the operator chose option 3. Steps 3, 4, and the
> acceptance runs that depend on a shipped row do not describe what shipped.
> The record of the executed work is below.
>
> **What was actually done, in order:**
>
> 1. Steps 1, 2, and 2b unchanged — the split and its six leftover-reference
>    reconciliations are what shipped.
> 2. `templates/.codex/sd-ai-command-pack/planning-adversarial-review-codex.md`
>    moved to `docs/planning-adversarial-review-codex.md`; `templates/.codex/`
>    removed entirely.
> 3. Step 3 reverted — the manifest row is gone; version 0.68.0 stays, since
>    the shipped host contract did change. Step 4's partition row went with it
>    (`grep -c planning-adversarial-review-codex docs/fleet/surface-partition.json`
>    → `0`).
> 4. `AGENTS.md` gained a maintainer-rules pointer to the appendix, inside the
>    link checker's `documentationRoots`.
> 5. `templates/.claude/rules/sd-planning-adversarial-review.md`: the
>    Codex-specific "Do not claim Codex approval" sentence generalized to any
>    lane, since consumers now have exactly one.
> 6. Host contract section 2 names no second-lane file at all. A conditional
>    link would dangle: under option 3 the appendix can never be present in a
>    consumer.
> 7. `tests/test_install_core.py` reverted to `main` — with no `codex`
>    manifest rows, `test_install_prints_platform_note_for_manifest_less_platform`
>    works unmodified again. `tests/test_claude_planning_review.py` keeps the
>    host-contract-carries-no-invocation test and replaces the three
>    install-behavior tests with
>    `test_appendix_is_absent_from_the_shipped_payload`, which asserts no
>    manifest row *and* no copy under `templates/`.
>
> **Measured after the re-cut:**
>
> ```
> shipped host contract: FIRES []
> shipped rule:          FIRES []
> unshipped appendix:    FIRES [24]
> ```
>
> Run through `codex_in_command_position` with the caller's own `commanded`
> set (`command_lines | direct_path_lines`). The appendix line proves the probe
> has bite; the two shipped files are clean.
>
> `make test` exit 0 (74 `OK` groups). `make check` exit 0, including
> `release changelog gate: manifest version bump has matching top heading
> '## 0.68.0 - 2026-08-11'` and `candidate ledger: valid`.

Ordered. Each step names the command that proves it and the result that
counts as failure. Step 1 is measurement and runs before any edit — a
baseline captured after the change proves nothing.

## 1. Baseline, before touching anything

Rerun the D0 probe against the unsplit template and record which lines
fire. Expect exactly one: line 42.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c '
import importlib.util
from pathlib import Path
p = Path("scripts/sd-ai-command-pack-thin-resweep.py")
s = importlib.util.spec_from_file_location("rs", p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
f = Path("templates/.claude/sd-ai-command-pack/planning-adversarial-review.md")
body = f.read_text(); lines = body.splitlines()
rel = ".claude/sd-ai-command-pack/planning-adversarial-review.md"
structured = m.structured_command_lines(lines, rel, body)
commanded = m.command_lines(lines) | m.direct_path_lines(lines, rel, body)
for n, l in enumerate(lines, 1):
    if m.CODEX_TOKEN.search(l) and m.codex_in_command_position(
        l, n, commanded, structured
    ):
        print("FIRES", n, l.strip()[:100])
'
```

Failure: more than one firing line, or a firing line outside the Codex
lane section. Either means the split boundary in step 2 is wrong and the
host contract would keep a marker.

## 2. Split the template

Move **lines 41–89** — the Codex lane inside section 2, measured, not
located by eye — into
`templates/.codex/sd-ai-command-pack/planning-adversarial-review-codex.md`.
Do not reword while moving: a moved paragraph that also changed is two
changes reviewed as one, and D2 rejected rewording on its merits.

The host contract keeps everything else and gains a **conditional "read
and follow" edge** to the appendix — not a mention of it. D3's C-5
disposition is the reason: the only mandatory lazy-load edge in this
surface is the rules file's "read and follow" link, and a sentence that
merely names a document creates no obligation to open it. The appendix
now lives under `.codex/`, so the edge crosses directories rather than
naming a sibling, and it is conditional on the file being present.

**The same sentence must say the file is not always there** — phrased as
"absent where the Codex platform was not installed", **not** "present
only where `codex` is declared". The narrow form is false: `--all` and
`--platform codex` install it without a declaration (D1), so shipping it
would put knowingly wrong availability guidance into every consumer's
copy. Round 3 caught this as C-13 — the round-2 fix for a dangling link
introduced a false claim in the sentence meant to prevent it. Not a link with a caveat a paragraph later: the one markdown-link check in `make check` does not cover this
file's directory (D3), so a reader who follows a dead link
has no signal distinguishing "deliberately absent" from "pack defect",
and the natural response to an apparent defect in a shipped contract is
a bug report. The availability condition and the link travel together or
the edge is not done.

That sentence names a document, never a command — and specifically not
`--platform codex`, which carries the `codex` token in command position
and would reintroduce the marker the split exists to remove. Restore
guidance belongs in the CHANGELOG (step 6), which consumers do not
carry, and D4.1's corrected table is what step 6 copies from: the durable
restore is a `docs/fleet/consumers.json` declaration, not the flag.

## 2b. Reconcile the references the move leaves behind

**This step is why step 1's probe is not sufficient on its own.** Several
lines name the Codex lane from outside the moved block and none of them
fires the detector, because they say "Codex" or "lane" rather than
`codex exec`. Excising 41–89 without touching them leaves a contract
that describes two lanes to a consumer that has one — and line 127
requires reporting the status of a lane it cannot attempt.

Enumerate them rather than working from a list, because a list written
now goes stale the moment the template moves a line:

```bash
F=templates/.claude/sd-ai-command-pack/planning-adversarial-review.md
grep -inE "codex|lane" "$F" | awk -F: '$1<41 || $1>89'
```

As measured on the pre-split template that is **six** lines, not the four
the first draft of this step named:

| Line | Text | Why it survives the excision |
|---|---|---|
| 20 | `## 2. Parallel review lanes` | The section heading itself. After the split the section describes one lane, under a title promising several. |
| 26 | "accepting either review lane at face value" | "Either" presupposes two. |
| 93 | "Merge and deduplicate both lanes into one concern ledger" | Instructs a merge of something that has one input. |
| 112 | "one fresh Codex review against" | Names the lane directly, in the remediation-round rule. |
| 118 | "the two lanes remain in material conflict" | A stop condition that can never trigger. |
| 127 | "Codex status as completed, skipped, or failed" | Requires reporting a lane the reader cannot attempt. |

Lines 20 and 26 are the ones the first enumeration missed, and they are
the two that matter most for readability: a heading and a presupposition
are exactly the kind of reference a `grep` for `codex` alone does not
return, which is why the command above searches for `lane` as well.

Make each conditional on the appendix being present. Section 2 already
has vocabulary for a lane that was skipped or failed; what it lacks is
vocabulary for a lane that was never installed, and that is the
distinction to add. Verify by reading, not grepping: a `codex`-free
rewrite of line 127 could still leave the requirement implied by its
surrounding list.

The appendix keeps its own copy of whatever it needs to stand alone, and
it may name the lane unconditionally — every repository that has the file
either declared `codex` or asked for it explicitly with `--all` or
`--platform codex`. Note the wording: *has the file*, not *declares the
platform*. D1's `--all` case means those are not the same set, and an
earlier draft of this paragraph said "read only by repositories that
declare `codex`", which is the narrowed claim C-2 already corrected
elsewhere.

## 3. Manifest row

Add one row to `manifest.json`, mirroring the existing pair's shape:

```json
{
  "platform": "codex",
  "kind": "doc",
  "source": "templates/.codex/sd-ai-command-pack/planning-adversarial-review-codex.md",
  "target": ".codex/sd-ai-command-pack/planning-adversarial-review-codex.md",
  "anchor": ".codex"
}
```

`platform: "codex"` is the gate; `anchor: ".codex"` matches the
convention but is **not** what makes this safe — D1's fact 3 is.

This is the pack's first `codex` row, and an earlier draft of this step
said only "watch for gates that assume the platform ships nothing",
which is a worry rather than a check. Two were resolved during round-2
planning, so the implementer inherits facts instead of a hunch:

- **Manifest platform validation accepts it.**
  `sd-ai-command-pack-surface-check.py:393` builds
  `known_platforms = set(registry.PLATFORM_REGISTRY)` plus `"shared"`,
  and rejects anything outside it (`:417`). `codex` is a registered
  `PlatformInfo` (`installer/registry.py:123`), so the row validates.
  What would have failed is a hand-maintained allow-list; there is none.
- **The command-surface drift check does not apply.** It is keyed on
  `SKILL_FANOUT_PLATFORMS` and `NEUTRAL_COMMAND_SOURCE_PLATFORMS`, not
  on every platform, and this row is `kind: "doc"` — no command surface
  is expected to fan out for it.

What remains genuinely unknown is whatever `make test` and `make check`
assert about the *shape* of the generated partition once a `codex` row
exists; step 5 runs them, and step 4 names the specific classification
that must come back.

## 4. Partition row — the target's directory is the design, not a preference

The appendix must **not** land under `.claude/sd-ai-command-pack/`. That
prefix is an unconditional `CONSUMER_CONFIG` override
(`partition-surfaces.py:115`), and `expected_residual_targets` adds a
`consumer-config` row to the expected residual without checking the
consumer's platforms (`installer/conversion.py:307`) — so an appendix
that was never installed would make expected and residual disagree and
`stale_receipt_reason` would refuse the conversion
(`install.py:959-961`). Same conversion, different blocker.

Under `.codex/` there is no override, so the row classifies through
`platform_category("codex")` = `repo-native`
(`partition-surfaces.py:143`), which *is* platform-checked. Confirm
after `make generate`: the row must appear as `repo-native`, not
`consumer-config`. A `consumer-config` classification here is the C-1
failure returning, and acceptance run 8 is what catches it if this check
is skipped.

Note that `repo-native` is in `KEEP_CATEGORIES`, so for a repository
that *does* declare `codex` the appendix survives conversion — and the
scan's `if "codex" not in declared` guard is what keeps it quiet there.

## 5. Propagate and gate

```bash
make sync && make generate
make test && make check
```

`make sync` runs `install.py . --force`, which per D4 **will not**
install the appendix into this repository. That is the designed outcome,
not a failure — but confirm it is the reason, by checking the run's
skip line names the platform rather than the anchor.

No manual mirror edits.

## 6. Version and changelog — before release-prep

`manifest.json` bump plus a matching top `CHANGELOG.md` heading. The
entry must name all three effects D4 records, not only the tidy one:

1. any repository whose developers have the Codex CLI on PATH loses the
   second review lane — accepted by the operator 2026-08-11;
2. the restore path, copied verbatim from D4.1's corrected table — a
   `docs/fleet/consumers.json` declaration **plus** the flagged refresh
   the fleet preflight emits, since declaring alone installs nothing; and
   the fact that an already-converted consumer must revert first
   (`install.py:1268-1273`). It lives here precisely because it cannot
   live in the shipped contract; and
3. the `install.py` hint all eight consumers gain, with the warning
   D4.1 records: following it installs the appendix **without** recording
   a declaration, and because the receipt entry then persists across
   later refreshes (`installer/provenance.py:313`), it re-arms the
   `undeclared codex usage` `packDefect` this release removes.

Do not write that the hint "costs the 75-target retention" — an earlier
draft of this step did, and it is the round-2 error C-12 corrected.
Retention is priced by the fleet declaration (`install.py:919`), not by
the flag. The hint's real cost is the one above: a blocked conversion
nobody decided on.

`make release-prep` validates the bump and heading in the same run, so
this precedes it. Note that the CHANGELOG is not a consumer-installed
surface, which is what makes it a safe place for the flag.

## 7. Acceptance measurement

Eight runs, numbered exactly as design's verification strategy numbers
them. Runs 4, 5, and 8 are the ones that would be skipped because the
diff looks complete.

1. **Not selected without the declaration.** A fixture with a populated
   `.codex/` — the canaries' exact shape — installed with no
   `--platform`: the appendix is absent and the skip reason names the
   platform. This is the claim the design rests on.
2. **Selected with it.** The same fixture under `--platform codex`: the
   appendix is present.
3. **Host contract clean.** The step-1 probe against the split host
   contract: zero firing lines.
4. **Appendix still fires.** The step-1 probe against the appendix: at
   least one firing line. If this comes back clean the split diluted the
   marker instead of moving it, which would mean the gate can no longer
   see real usage — stop and re-plan.
5. **The host contract still reads as a whole.** Read it end to end and
   confirm two things, not one: (a) no step, list item, or report field
   requires a lane the reader may not have, and (b) the sentence that
   links the appendix states *in that same sentence* that the file is
   not always present, phrased so it stays true for a repository
   installed with `--all` or `--platform codex`. Part (b) is separate
   because
   an implementation can satisfy every other line of step 2 and still
   emit a bare link — and the repo's markdown-link check excludes this file's
   directory (D3). No probe closes (a) either: none of step 2b's six references
   ever fired the detector, and a `grep` for `codex` alone returns four
   of the six — it misses the section heading on line 20 and the "either
   review lane" on line 26, which are precisely the two a reader
   notices first.
6. **Fleet.** `packDefects` reports no `codex` row for any of the eight.
7. **Disjoint.** The seven-surface count is unchanged from
   `08-10-thin-prompt-surface-repoint`'s post-merge state.
8. **The conversion is not refused on receipt drift.** On a fixture
   installed normally (no `--platform`, no `--all`), run
   `install.py <fixture> --check --json` and a gated `--thin`: both must
   succeed. This is C-1's regression check, and it is listed separately
   because a file-selection probe cannot see it — the appendix's absence
   is *correct* selection and *incorrect* residual accounting at the same
   time, and only `expected_residual_targets` versus the receipt tells
   them apart. Failure here means the partition placement is wrong again.

Run 8 exists because the adversarial review's C-1 was a defect the
original plan's own acceptance runs would have passed. Runs 1–4 all
check what gets installed; none of them compares expected residual to
receipt. Run 5 exists for the same reason one round later: round 2 found
step 2b's reference list was two short, and no automated check in this
list would have caught that either.

Runs 6 and 7 need a consumer carrying this version. No consumer is on it,
and putting one there mutates a repository this task holds no
authorization for — the same boundary
`08-10-thin-prompt-surface-repoint` hit. Measure both on the disposable
fixture here, and let children 3–5 close the fleet half through each
consumer's pre-conversion resweep, which already gates on it. State the
residual gap rather than implying the fixture stands in for the fleet:
the fixture cannot see a consumer installed with `--all` (D1's third
case) or one whose developers run Codex without declaring it, and both
are consumer-specific facts only that consumer's own resweep reports.

## Rollback

Every edit is a text change under `templates/`, one manifest row, and
generated mirrors. `git revert` of the merge commit restores the previous
shipped payload; the version bump reverts with it. A consumer that
already refreshed keeps a file the revert stops shipping — harmless,
since the host contract is unchanged and a retained appendix is a
self-contained document that names its own preconditions.

Do not write "the appendix was never installed where `codex` is
undeclared" here, however true it feels: `--all` installs it regardless
(D1), so the rollback has to be correct for a repository that has the
file without the declaration. It is — the file is inert on its own, and
the resweep reporting it is the gate working, not the rollback failing.
