# Implement — the plan interview is one sentence

## Budget

**Nothing this item does is capped, and that is why the figure is derived
rather than waved through.** `tests/test_loc_caps.py` defines four ceilings and
they cover `bin/`, `bin/migrate-*`, `dashboard/` and `dashboard/`'s code half.
The whole of the remaining work lands in
`docs/work/2026-09-04-the-plan-interview-is-one-sentence/prd.md`, which no
ceiling reaches. Measured at `405a9106` with the test module's own functions,
`bin/` stands at **17,216** against `BIN_CAP` **18,000** — 784 of headroom, none
of it claimed here, because no line under `bin/` or `dashboard/` moves. That is
the acceptance criterion about `git diff --stat origin/main...HEAD -- bin/
dashboard/`, and it is what checks this paragraph.

So the number below binds nothing mechanical. It is derived anyway, by the
method in `tests/test_loc_caps.py` — a named built analogue per span, glue at
the target file's own measured rate, body variance, post-report discovery —
because "a small documentation amendment" is exactly the kind of claim that
turns into four hundred lines while everybody agrees it is small, and because
the analogues are all in `prd.md` itself and cost one measurement each.

**The body is 29, six spans at analogues measured in `prd.md`.** Every analogue
is drawn from the file the change lands in. Where a span replaces existing text,
both figures are given and the body carries the net.

| span | finished | replaces | net | analogue |
|---|---|---|---|---|
| the relocation note under `## Acceptance criteria` | 6 | 0 | 6 | criterion 4's own bullet in this file, **6** lines — the file's built example of a criterion that carries the reasoning for its own form. Criterion 7 at 13 is the other candidate and is rejected: it carries a fenced command block and this span carries none |
| six criteria re-pointed `skills/` → `contrib/` | — | — | 0 | a one-token in-place substitution in six bullets. No line is added or removed; the six keep their shapes, their commands and their expected results |
| criterion 1 rewritten off the pinned `40` | 4 | 1 | 3 | criterion 5, **4** lines, this file's built example of a criterion that states when it is evaluated and why |
| criterion 4 retired, with the commit it was met at and the item that owns its removal | 9 | 6 | 3 | criterion 4 itself at **6**, plus 3 for the trigger-and-owner shape `## Review` already uses at C-7 ("Trigger: … Owner: …") |
| requirement 7's retirement sentence | 4 | 0 | 4 | C-6's rebuttal block in `## Review`, **4** lines — one finding, one sentence of evidence, one disposition, which is the same shape |
| the `## Log` entry | 13 | 0 | 13 | the **median** Log bullet across the six active items' `prd.md`, n=127. The mean is 27.28 and is the wrong statistic: the distribution runs from 2 to 425, and two entries over 250 lines drag it past every value in the middle |

**Glue is 3, at `prd.md`'s own measured rate.** The file is 291 lines holding 40
text blocks separated by 39 blank lines — **0.975** blank lines per block. Three
of the six spans open a new block (the relocation note, the requirement 7
sentence, the Log entry); the other three are edits inside existing bullets and
open none. 3 × 0.975 = 2.9, so **3**. The file's own rate is used rather than a
rate across `docs/work/`, for the reason R11-D46 gives for using
`bin/sd-status`'s 5.21 instead of its class mean: every line of this change
lands in one file, and pricing it against files it does not touch prices
somebody else's change.

**Seam is 0.** A seam charge buys the discovery behind a boundary that has not
been crossed before. Every span here is an edit to a markdown file this item
already owns, and every gate that will read it — `bin/sd-docs-lint` rules 1, 2,
6 and 7 — already runs over this directory on every `make check`. The one
boundary that would have been new is `skills/paths.json` and a `git mv` of a
skill directory, and the design rejects that approach (D1), so it is not
crossed and not charged.

**Body variance is 26%, and the figure is borrowed.** 26% of 29 is 7.5, so
**8**. The only observed series in this repository is R11-D45's and R11-D46's
four code spans — PR 8a −2%, 8b +26%, 8c −19%, 8d −11% — sized to the largest
overrun rather than to the mean, because an underrun costs unspent budget and an
overrun costs a re-derivation. **There is no docs-specific series**, and this
line does not pretend otherwise: four observations of Python bodies are being
applied to a markdown amendment because they are the only observations that
exist. A reader who thinks prose varies more than code should read this figure
as a floor.

**Post-report discovery is 5.5%, and the figure is borrowed on the same
terms.** 5.5% of 29 is 1.6, so **2**. R11-D46's mean of six: 14.4%, 8.3%, three
zeroes, and 10.6%.

29 + 3 + 0 + 8 + 2 = **42 lines**, all under `docs/work/`, none under any
ceiling.

**These two planning pages are not in that figure.** `design.md` and
`implement.md` are the deliverable of the planning commit; the 42 is the
implementation commit that follows. Their own size is a fact rather than a
budget, and it is recorded in `## Verification results` on the run that writes
them, so a later reader can see what the planning cost as well as what the work
did.

## Step checklist

Each step is landable on its own and green on its own. Steps 1 through 5 all
edit `prd.md` and all leave `make check` and `bin/sd-docs-lint` clean at every
point, because none of them changes a shape either gate reads. They are
separate steps because they are separate claims, not because they need separate
commits; step 6 is what makes them one pull request.

- [x] **1. Record the baseline before touching anything.** On this worktree at
      `origin/main`: `make check`, then `grep -cE '^OK' unittest-output.log` and
      `grep -c FAILED unittest-output.log`, and
      `.venv/bin/python bin/sd-docs-lint`. Write the three results into
      `## Verification results` on this page. Landable and green on its own: it
      changes one planning page and no criterion. It is first because the `OK`
      count after the change is meaningless without the count before it.
- [x] **2. Verify the ruling still says what the design quotes.** This exact
      command prints `1`:

      ```
      grep -cF -- '`sd-grill` moves to' \
        docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md
      ```

      and the sentence it matches names `contrib/`, a trial, and the operator's
      decision on 2026-09-05. It is a fenced block and not an inline span
      because the pattern itself contains backticks, and an inline span carrying
      one is not the command it appears to be — which is C-9 on this item in
      miniature. That document is `in_progress`, so this is checked at
      implementation time and not taken from the design. **If it no longer says
      it, stop.** The design rests on it; a changed ruling is a new design, not
      a step that adapts.
- [x] **3. Re-point six criteria and add the relocation note.** In `prd.md`,
      `skills/sd-grill/SKILL.md` becomes `contrib/sd-grill/SKILL.md` in the
      criteria for `disable-model-invocation`, the title, the lineage, the seven
      classes, `## Safety rules` and the gate sentence. Add the note under
      `## Acceptance criteria` saying the criteria name `contrib/` because the
      2026-09-05 operator ruling moved the file, quoting the ruling and naming
      the item that carries it. Criterion 4 is untouched here: it names
      `skills/sd-plan/SKILL.md`, which does not move.
- [x] **4. Repair criterion 1, and retire criterion 4.** Criterion 1 drops the
      pinned `40` for the invariant: `grep -c FAILED unittest-output.log` prints
      `0`, and the `^OK` count is unchanged across this item's own change, with
      the baseline from step 1 named. Criterion 4 gains the commit it was met at
      (`405a9106`) and the sentence retiring it, naming the 2026-09-05 ruling
      and `docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person` as
      the owner of the removal. Requirement 7 gains the matching sentence.
      Nothing under `skills/` is edited (design D4).
- [x] **5. The `## Log` entry.** Dated 2026-09-07: the work shipped in `8cf99431`
      and `cec8721e` and closed no item because the merge carried no `Delivers:`
      trailer; `05eb8ddf` moved the file; the 2026-09-05 ruling is why the
      criteria follow the file rather than the file coming back; and the two
      planning pages exist because the approach stopped being obvious the day
      the ruling was made.
- [ ] **6. Close it.** One pull request carrying the amendments, with
      `Item: 2026-09-04-the-plan-interview-is-one-sentence` — which
      `skills/sd-ship/SKILL.md:82-84` puts on every merge it makes, and which
      step 6 had omitted — and
      `Closes: 2026-09-04-the-plan-interview-is-one-sentence` on the merge, and
      **not** `Delivers:`. `skills/sd-ship/SKILL.md:84-89` gives `Delivers:` to
      the one merge that delivers, closing the item "on that merge and on no
      other", and makes `Closes:` the remedy for a delivery whose merge went out
      without the trailer. The delivering merge was #740. `Delivers:` cannot be
      issued retroactively onto a later merge without making two merges each
      claim to be the delivering one, which is the thing the skill's "on no
      other" forbids; `Closes:` is the line the skill provides for exactly this
      case, and carrying both would make it redundant against its own rule. Then, and only once the
      remote has confirmed the merge, the row goes to `done` through `sd_db`'s
      `transition`, with `shipped_at`. No `status:` line is written into
      `prd.md`: `docs/work/.status-source` says `row`, and `bin/sd-docs-lint`
      rule 1 fails an active item that carries one.

## Verification

Named before the work, and each names its own result.

1. `.venv/bin/python bin/sd-docs-lint` → exit `0` and a final line reading
   `sd-docs-lint: clean`. Run before step 3 and after step 5. The rules at risk
   are 1 (the item holds only `prd.md`, `design.md`, `implement.md` and
   `.citations.tsv`, and the frontmatter carries no `status:`), 2 (a workable
   item states acceptance criteria and has no open blocking line) and 7 (every
   `docs/work/` path the amended text names resolves — step 4 adds a reference
   to another item's directory, which is the one new path this change
   introduces).
2. `make check` → `grep -c FAILED unittest-output.log` prints `0`, and
   `grep -cE '^OK' unittest-output.log` prints the same number as step 1's
   baseline. The number is **not** pinned here for the same reason criterion 1
   stops pinning it: `tests/` tracks 56 modules today and tracked 40 when this
   item was written, and a figure written down here would rot on the same
   schedule. What is asserted is equality with the recorded baseline, and this
   change adds no test module.
3. Each amended criterion, executed by copying its text out of the amended
   `prd.md` rather than retyping an equivalent → the result the criterion
   states. Expected: `0` for `disable-model-invocation`; `1` for the title; `1`
   for the lineage line, which must also read `MIT` and `b36e082`; seven lines
   each ending `1` for the class loop; `1` for the gate sentence; the
   `## Safety rules` section present with a read-only first rule; `1` for
   criterion 4's `sd-plan` sentence. C-9 on this item was a criterion verified by
   running a different command from the one written down, so copying rather than
   retyping is the check, not a convenience.
4. `git diff --stat origin/main...HEAD -- bin/ dashboard/` on the pushed branch
   → prints nothing. Evaluated after the commits exist, per C-8: before them it
   prints nothing whatever the tree holds. Under this plan it prints nothing for
   the honest reason, since every changed file is under `docs/work/`.
5. `git diff --stat origin/main...HEAD --name-only` on the pushed branch → every
   path begins `docs/work/2026-09-04-the-plan-interview-is-one-sentence/`. This
   is what proves design D4 — that the `sd-plan` sentence was not deleted here —
   and it is a stronger check than reading the diff, because it fails on any
   file under `skills/` rather than on the one line somebody remembered to look
   for.
6. `grep -c '^status:' docs/work/2026-09-04-the-plan-interview-is-one-sentence/prd.md`
   → `0`, after step 6's row transition. The row is the status; a `status:` line
   would be a second answer, and rule 1 fails it.
7. After the merge, `.venv/bin/python bin/sd-status` → the item prints under
   `work items` as `done`. The active count is **not** asserted and does not
   move: `bin/sd-status:170` counts non-archived *directories*, and
   `skills/sd-ship/SKILL.md:86` says closure writes nothing into a file and the
   directory stays. Measured today, `active` is 6 over 497 items with
   `counts {done: 493, in_progress: 2, planning: 2}` — 493 closed items sit
   inside that 6 already. A closure that moved the number would mean step 6 had
   archived something, which it does not do. It must be the
   virtualenv interpreter: `sd_db` lives there, and the system `python3` cannot
   import it, falls back to git and reports this item `in_progress` today where
   the row says `planning`. Both were run at `405a9106` and disagree, which is
   itself the reason the check names its interpreter.

   **Not `branch-already-merged`.** An earlier draft of this page verified the
   closure by counting that check's findings.
   `grep -n 'branch-already-merged' bin/sd-status` returns nothing: the check is
   unbuilt work in
   `docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first`, which is
   still `planning`. Naming a check that does not exist is a verification that
   cannot fail, and this item's own C-9 was the same mistake.

**Not verifiable here.** That the amended criteria are the *right* criteria —
that re-pointing six paths is a correction and not a bar being lowered — is a
judgment, not a check. The design argues it and the review tested the argument;
what would settle it is the user's reading, and nothing in this repository can
stand in for that. Likewise, whether the 2026-09-05 ruling should be revisited
now that `skills/sd-plan/SKILL.md` still names a skill that no longer installs
is the operator's call and not this item's; step 2 checks that the ruling still
says what it said, and cannot check whether it should.

## Verification results

Filled in as each check runs, so a claim here is a transcript and not a plan.

- 2026-09-07, planning commit, before any `prd.md` amendment:
  `.venv/bin/python bin/sd-docs-lint` → `sd-docs-lint: clean`, exit `0`.
  `make check` → exit `0`, `grep -cE '^OK' unittest-output.log` = `56`,
  `grep -c FAILED unittest-output.log` = `0`. That `56` is the baseline
  verification 2 compares against.
- 2026-09-07, step 1 re-run on `main` at `5c23df19`, which is the commit this
  branch left from and therefore the baseline the criteria actually name:
  `bin/sd-docs-lint` → `sd-docs-lint: clean`, exit `0`; the test script → exit
  `0`, `^OK` = `56`, `FAILED` = `0`. Unchanged from the planning commit, so the
  `56` above survives four merges and is still the number criterion 1 compares
  against.

  A fresh worktree has no `.venv`, and `make check` there fails on the missing
  interpreter rather than on anything it measures: `error: PYTHON_BIN must
  resolve to an executable (got '.venv/bin/python')`. The `Makefile` declares
  `VENV ?= .venv`, so the primary checkout's environment is borrowed by
  overriding it, and this is the exact command that produced the line above:

  ```
  make check VENV="$HOME/repos/platypeeps/sd-ai-command-pack/.venv"
  ```

  `bin/sd-docs-lint` is run the same way, as
  `"$VENV/bin/python" bin/sd-docs-lint`. Spelled out because a transcript that
  cannot be re-run is a claim rather than a check. Found in review.
- 2026-09-07, step 2's gate, on `main` at `5c23df19`: the `grep -cF` command
  prints `1`, and the sentence it matches — *"`sd-grill` moves to `contrib/` and
  a trial decides whether it stays, by the operator's decision on 2026-09-05"* —
  names `contrib/`, a trial, and the 2026-09-05 decision. The design's
  foundation still holds, so steps 3 through 5 proceed.
- 2026-09-07, step 3's six re-pointed criteria, each run against
  `contrib/sd-grill/SKILL.md`: `disable-model-invocation` → `0`; `^# sd-grill$`
  → `1`; `obra/superpowers` → `1`; `This holds at every classification` → `1`;
  the seven-class loop → seven lines each ending `1`; `## Safety rules` present
  at `:217` with the read-only rule first. All six pass at the new path, which
  is what says the move — and not the criteria — was the whole of the problem.
- 2026-09-07, the two planning pages at `7cd1f5c1`, `wc -l`: `design.md`
  **599**, `implement.md` **228**. Both figures are pinned to that commit and
  are already stale at HEAD, which is the property rather than a defect to fix:
  a line count of the file it is written in cannot be kept true by the file
  that reports it, and rounds 4 and 5 changed both pages. Read them as the
  measurement at the commit named, not as a current figure.
  Outside the 42-line budget above, which prices the
  `prd.md` amendment only. 599 is long for a design and 210 of it is the
  `## Review` ledger, which starts at line 390 — what three rounds against one
  lane cost when the third round's finding is that the first two produced no
  ledger at all. The 210 was itself a sweep finding: the first draft of this
  bullet said 236, arrived at by subtracting the wrong line number.
- 2026-09-07, after the planning pages were written:
  `.venv/bin/python bin/sd-docs-lint` → `sd-docs-lint: clean`, exit `0`;
  `make check` → exit `0`, `^OK` count `56`, `FAILED` count `0` — the same two
  figures as the baseline, which is verification 2's assertion holding across
  the planning commit as well as the implementation one.
