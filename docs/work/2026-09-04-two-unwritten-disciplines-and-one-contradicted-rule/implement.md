# Implement — two unwritten disciplines and one contradicted rule

## Step checklist

- [ ] **Step 1 — the question-form rule in `sd-grill`.** One file. Add the
      open/closed distinction and its three cases to the question rules, make an
      assistant-authored option set contaminate by construction under the
      existing contamination rule, require a fully contaminated `completed`
      session to say so ahead of the requirements it presents, add the matching
      red-flags row, and record in Lineage what the sources actually say — they
      pull in different directions without contradicting each other, and the
      defect was this skill's own ambiguity rather than an inherited one. Independently landable: it corrects a shipped skill and depends
      on nothing else in this item.

- [ ] **Step 2 — `sd-debug`.** One new `skills/sd-debug/SKILL.md`. The
      reproduction gate, the hypothesis ledger with its falsifying prediction,
      one variable per experiment, the evidence classes, the three closing
      states, the red flags, the bound on outward action, and the seams to
      `sd-postmortem`, `sd-retro`, `sd-check`, `sd-review`, `sd-red-team`,
      `sd-plan` and the `sd-rust-*` family. Independently landable and green on
      its own.

- [ ] **Step 3 — `sd-receive-review`, and the pointer back from
      `sd-feedback`.** One new `skills/sd-receive-review/SKILL.md` reusing the
      planning contract's four dispositions, the steelman rule, the
      authority-is-not-evidence rule, the escalation-only `unresolved` state,
      and the bound on outward action, plus the seams to `sd-feedback`,
      `sd-red-team`, `sd-grill`, `sd-debug`, `sd-review` and `sd-ship`. Plus one
      line in `skills/sd-feedback/SKILL.md` naming this skill as the owner of
      the job it already disclaims. Landable independently of steps 1 and 2; the
      `sd-feedback` edit lands with it rather than separately, because a pointer
      to a skill that does not exist yet is worse than no pointer.

- [ ] **Step 4 — the `bounds=` reservation in the shared vocabulary.** One line
      in `skills/_shared/references/argument-vocabulary.md` reserving `bounds=`
      and distinguishing it from `scope=`. This is not a one-file edit in
      effect: `bin/sd_install.py` fans the shared reference out to every skill
      citing it, so the installed companion changes for all 56 citers across
      both the Claude and Codex directory layouts. Two things to do, not one —
      make the edit, then audit the consumers: enumerate the literal `bounds=`
      uses from the tree (`grep -rn 'bounds=' skills/`) and confirm each matches
      the reserved meaning rather than assuming it.
      `tests.test_skill_companions` proves the copy happened and proves nothing
      about the meaning. Lands with steps 2 and 3, which are two of the four
      uses.

## Verification

Named before the work, and each is decisive for what it covers.

**Structural, for all three steps.** `python3 -m unittest
tests.test_skill_frontmatter` prints `OK` — this is the check that catches the
most likely mechanical error, a `name:` that does not match its directory or a
first heading that is not exactly the directory name. `ls skills/*/SKILL.md |
wc -l` prints `81`, which catches a directory created in the wrong place —
counted as skill files, because `ls -d skills/*/` also counts `skills/_shared/`,
which is companion references and not a skill. `make check`
ends with 0 `FAILED` and 40 `OK`, which catches a new skill breaking an existing
suite and catches a lost test module.

**Content, per requirement.** Every command block in the PRD's acceptance
criteria, run exactly as written and its output quoted — the five phrase groups
(`sd-grill` section-bound, `sd-debug` states and gate, `sd-receive-review`
dispositions, the remaining clauses of requirements 5, 7, 8 and 10, and the
anchored section skeleton), plus the seam and reciprocal-pointer greps and the
two `git diff --name-status` path-identity commands.

They are fixed-string and whitespace-flattened on purpose. The earlier
`sd-grill` item shipped a criterion whose unquoted `.` matched as a wildcard and
another that was "verified" by running a command different from the one written
down; this item's first draft then shipped three criteria that a line break
defeated. All three classes were caught by a review lane rather than by the
author, which is the argument for running each block verbatim rather than
running something equivalent to it.

**Budget.** `git diff --stat origin/main...HEAD -- bin/ dashboard/
tests/test_loc_caps.py` prints nothing on the pushed branch. The ceilings live
in `tests/test_loc_caps.py`, outside the first two paths, so a pathspec without
it would pass while a ceiling was raised. This item adds no Python, so any output at all
means something was edited that should not have been.

**What cannot be verified here.** Whether an agent holding these skills behaves
differently. There is no conduct harness in this repository and the item that
would have built one was abandoned; `claude plugin eval` implements it and is
gated behind early access on this account. Requirements 5 through 8 and
requirement 10 are therefore reader-verified — 10 is a rule about how a question
is *asked*, which no grep over the file reaches — and that is stated in the PRD
rather than papered over. This item leaves the pack with three skills in that
condition instead of one.

## Closing steps

- Drop the `branch:` field from `prd.md` frontmatter in the same edit that sets
  `status: done`; a truthy `branch:` on a done item silences the archive sweep.
- If a review lane blocks on one of the three steps, split that step into its
  own item and land the other two rather than stalling all three — the risk is
  named in `design.md` and this is the response it names.
