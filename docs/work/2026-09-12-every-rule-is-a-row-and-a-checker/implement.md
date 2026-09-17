# Implement — every rule is a row and a checker

## Step checklist

- [x] **1. The empty registry and its own tests.** Add the registry table with
      zero rows, and the test asserting every row's checker resolves to a
      declaration that exists. Zero rows passes. This step is independently
      landable and independently green, and it fixes the shape before any rule
      argues about content. It also carries requirement 1's check: a rule id
      appearing as a literal in tracked code outside the registry module is a
      failure.
      Verify: the new tests pass; mutation — add a row naming a checker that
      does not exist, confirm `test_every_live_rule_names_a_checker_that_exists`
      reddens; separately, paste a rule id literal into a consumer and confirm
      the second-list test reddens. Remove both and `diff -q` reports the tree
      identical. (As delivered, the checker was the function object and the
      first mutation failed at *import*. Since 2026-09-13 it is a
      `path::symbol` string, so the same mutation fails in the test named
      above — the check moved, the mutation did not.)
      **Delivered `bb379027` (#882), 2026-09-12.** `bin/sd_rules.py` carries
      `RULES` and `BY_RULE_ID`; `tests/test_rule_registry.py::Registry` carries
      the checker-resolution test and the second-list test.

- [x] **2. Meta-check legs a and b, with the baseline.** Leg a: every registry
      row is cited by at least one skill. Leg b: every tool-behaviour claim in
      a skill cites a rule id the registry carries.
      **The baseline is `UNCITED_SKILL_CLAIMS`, a projection of `claims_in`
      and not its return value.** `claims_in` finds every claim, cited or not;
      `uncited_skill_claims()` keeps the ones citing no id and counts them per
      document. It counts *violations* within leg b's scope —
      the claims in `skills/` citing no rule id — and never the *population*.
      A ratchet over the whole live-prose population would be wrong twice: it
      counts claims leg b never examines, and adding a new, correctly cited
      claim would redden it.
      Verify: each leg reddens under its own mutation; the baseline test
      reddens when a document's uncited count RISES; adding a correctly cited
      claim does NOT redden it, which is the control that separates a
      violation count from a census.
      Do not verify against a 263→264 mutation. That instruction stood here
      until 2026-09-12 and cannot be run: 263 was never reproducible, so there
      is no such transition to induce. The correction below has the history.

      > **Correction, 2026-09-12 (sd:622).** 263 could not be reproduced, and
      > the three readings offered in its place could not be reproduced either:
      > an independent reconstruction of the same three shapes gave different
      > figures again, because each reconstruction had to invent the counting
      > rule the original never recorded. The shape of the requirement is
      > unchanged — violations, not population, downward only. The number is
      > now `UNCITED_SKILL_CLAIMS`: the per-document count `uncited_skill_claims()`
      > projects from `claims_in`, and the three properties of that predicate that
      > were load-bearing and unstated are pinned by `TheClaimPredicate`.
      > `design.md` carries the correction in full.

      **Delivered `bb379027` (#882) and corrected in `d745474b` (#889),
      2026-09-12.** `LegA` and `LegB` run the two legs, `TheClaimPredicate`
      pins the three load-bearing properties, and the baseline is
      `UNCITED_SKILL_CLAIMS` in `tests/test_rule_registry.py`.

- [x] **3. Meta-check leg c, over the R-id corpus.** Every rule id cited in live
      prose is defined in the registry. On the first run this reports 4
      failures — `R11-D1`, `R11-D30`, `R11-D46`, `R5-D1` — and a baseline of 26
      archive-only definitions. Verify: the run names exactly those 4 ids.
      **Delivered `bb379027` (#882), 2026-09-12.** `LegC` runs it, and the two
      baselines it carries — `DANGLING_RULE_IDS` and `STRANDED_RULE_IDS` — are
      sets rather than counts, so a resolved id cannot hide a newly stranded
      one. Measured on `075eecf2`, 2026-09-14: the dangling set is still the
      same 4 ids, and the stranded set is 20, down from the 26 this step first
      reported.

- [ ] **4. The R-id backfill.** Move live rule definitions out of archived
      planning documents into registry rows, one at a time, deciding for each
      whether it is a live rule or a historical decision. This is the expensive
      step. It lands in slices; each slice reduces the leg c baseline and the
      baseline test proves it fell.

      **Slice 1, 2026-09-12. `STRANDED_RULE_IDS` 26 → 25.** `R10-D5` is a
      row. It was already taught by a skill section that cites the id, and its
      checker is a plain function in `bin/` — `sd_setup_github.setup_github` —
      that is runtime code carrying its own refusal. Registering it turned the
      second-list check red on the refusal message in `bin/sd_setup_github.py`,
      which carried the id inside a string; the citation moved to the comment
      above it, which is the rephrasing that check's own failure text
      prescribes.

      `R10-D6` was a row for one review round, was pulled, and came back in
      slice 2. The first row named `sd_lib.repo_root` as its checker, and
      `repo_root(start=None)` accepts a path: it is the resolver the rule
      constrains, not a guard, so the row named the mechanism by which the rule
      would be broken as its enforcement. The meta-check passed it because the
      checker test asserts the checker EXISTS and never that it ENFORCES. Slice
      2 is that fix, and `R10-D6` is its first beneficiary rather than its
      casualty.

      **Slice 2, 2026-09-13. `STRANDED_RULE_IDS` 25 → 24, and the hole that
      admitted the bad row is closed.** Three changes, in the order they depend
      on each other:

      1. `Rule.checker` is a `path::symbol` string, resolved by
         `source:tests/test_doc_citations.py::source_declaration_error` — the
         resolver the pack's documentation citations already use. The callable
         form made `bin/sd_rules.py` import every checker's module at load time,
         and it could not name an extensionless entrypoint or a test at all.
      2. `Rule.proof` is new and required beside a checker: the mutation that
         makes that checker redden, in one sentence a reader can execute.
      3. Leg d runs it. For every live row with a checker it copies the tree,
         runs the named test clean, applies the mutation, requires the test to
         go red, restores the text and proves the copy identical again. It runs
         in a copy because `.github/scripts/run-tests.sh` shards the suite by
         module across workers, so editing `bin/` in the live tree would be
         editing it while another shard imports it.
         The leg carries its own control: a sentinel edit to a docstring in the
         same file, run through the same machinery, must leave the same test
         green. Without it, any failure to start a child would read as every
         checker enforcing.
         **The copy is per row, and its cost is budgeted nowhere.** Leg d
         dominates the module's runtime for three rows, and steps 5 and 6 would
         add roughly eight more; the cost is linear in rows, because each row
         copies every tracked file afresh.
         **Decided 2026-09-14 (owner, note 1989):** leg d takes one
         tracked-file copy per run rather than one per row, and then states the
         budget. Sharing the copy removes most of the cost without weakening
         the leg — each row still runs clean, mutates, reddens and restores —
         and step 7 needs a stated budget in any case.
         **Landed 2026-09-16, slice C.** `LegD.setUpClass` makes the copy once
         and `source:tests/test_rule_registry.py::exercise` takes it as an
         argument; `source:tests/test_rule_registry.py::TheSharedCopy` counts
         one copy over three rows and two controls, and read five on the base.
         The restore proof after every row is what keeps sharing as strong as
         copying, and a third control leaves a byte in the copy and requires
         that proof to fail. The budget is in `design.md`'s leg d decision.

      `R10-D6` is a row on that basis. Its checker is
      `tests/test_verb_inventory.py::test_no_command_accepts_a_repository_path`,
      and its proof renames `--belongs-to` in `bin/sd_work.py` to the banned
      spelling, which that test's `iterdir()` scan of `bin/` finds.

      **Two obstacles decide the rest of the backfill, and neither is the
      judgement the step was sized for.** The sentence that stood here counted
      "twenty of the twenty-four ids left after slice 2" and listed four taught
      ids, one of which — `R10-D4` — had become a row in the slice below it.
      Both figures are retired. Re-measured against `075eecf2` on 2026-09-14 by
      running the module's own enumerators —
      `source:tests/test_rule_registry.py::cited_rule_ids`,
      `source:tests/test_rule_registry.py::defined_rule_ids` and
      `source:tests/test_rule_registry.py::registered_rule_ids` — over the
      corpus, rather than by arithmetic on the old numbers:

      | Fact, on `075eecf2` | Count |
      |---|---|
      | Distinct rule ids cited in live prose | 45 |
      | Distinct rule ids defined by the bold-run form anywhere | 51 |
      | Registry rows | 3 |
      | Stranded — live citation, archive-only definition, no row | 20 |
      | Of the stranded, taught by no file under `skills/` | 17 |
      | Of the stranded, taught by some file under `skills/` | 3 |
      | Dangling — live citation resolving to no definition at all | 4 |

      The last two rows are the weakest measurement here and are written down
      as such. "Taught" is a substring scan of every markdown file under
      `skills/`, which is not what leg a reads: leg a requires the id in the
      *body* of the one section a row names. An id appearing in a skill outside
      any section a row could name counts as taught in this table and would not
      pass leg a. So 3 is an upper bound on the taught set and 17 a lower bound
      on the untaught one, and a slice registering one of the three confirms it
      against leg a rather than against this row.

      Seventeen of the twenty are taught by no skill section, so leg a cannot
      pass for them: registering one means writing the teaching section first,
      which is step 8 and not this step. That is why step 8 moves ahead of the
      rest of this step — see the owner decision recorded on it below. The other
      three are taught, and each is held up by something specific:

      | Id | Taught in | Why it is not a row yet |
      |---|---|---|
      | `R10-D1` | `skills/sd-status/SKILL.md` | `bin/sd-status` carries the id in two strings, one of them the `CLASSES` row whose text the skill's table mirrors. The second-list check wants it out of the string; leg a reads the skill table it would have to change. **Decided 2026-09-14 (owner, note 1989):** rewrite the `CLASSES` row and the reason string to drop the literal id and keep the citation in the adjacent comment — the rephrasing the check's own failure text prescribes, and what `R10-D5` did — and only after sd:10 retires the planning-age sweep, because `bin/sd_sweep.py` owned the threshold this rule constrains at the time (pack #995 has since moved it into `sd_lib`). **Landed 2026-09-16, slice D**, after pack #995 cut the sweep; see the Slice D paragraph below. |
      | `R10-D2` | `skills/sd-handoff/SKILL.md` | The section that teaches it says Lane B is *not implemented*. A live row with a checker would assert an enforcement that does not exist, which is the defect this item is about. **Decided 2026-09-14 (owner, note 1989):** it is repealed in the registry — `state=REPEALED`, no checker. Leg c still resolves the citation; leg a skips a repealed row; and a live false enforcement claim becomes an answered citation. This is the first use of the tombstone state the design says must exist before the first repeal, not after. **Landed 2026-09-16, slice B**, see the paragraph under S2 below. |
      | `R10-D3` | `skills/sd-handoff/SKILL.md` | Its enforcement lives in `bin/sd-handoff-restore`, which has no `.py` suffix. **The import obstacle recorded here is gone** — a `path::symbol` location needs no import and the path needs no suffix. What is left is leg d: the row needs a mutation that reddens a named test, and finding one for a restore path is the work. |

      **A stranded id no earlier revision of this document names: `R10-D7`.**
      It is in `STRANDED_RULE_IDS` and was not in the table above, so the claim
      that "each of the others carries a recorded reason here" was false for
      one id. The reason, measured on `075eecf2`: `bin/sd-review` cites it in
      the docstring of `local_conventions`, and its only definition is an
      archived design document. No file under `skills/` mentions it, so it is
      one of the seventeen untaught ids and it is blocked behind step 8 like
      the rest of them — not behind anything specific to itself. One thing is
      already settled for it: the citation is in a docstring, which
      `source:tests/test_rule_registry.py::second_list_entries` reads as a
      citation rather than as data, so registering it would not redden the
      second-list check the way `R10-D5` and `R10-D1` did.

      **Slice 3, 2026-09-13. `STRANDED_RULE_IDS` 24 → 23.** `R10-D4` is a
      row. Its checker is `bin/sd-review::codex_preflight`, the first checker
      the registry names in a file with no `.py` suffix, and the string form
      resolved it with no change to the resolver. Its proof replaces the
      `auth_mode` guard in `bin/sd-review` with a condition that is never true,
      and `test_a_non_chatgpt_auth_mode_refuses` in
      `tests/test_sd_review_codex.py` goes red on that edit. It fails an
      assertion, `Refusal not raised`, and does not raise an error. A sentinel edit to
      the same function's docstring leaves that test green. That was measured
      once, through leg d's `exercise()` from a scratch script on this branch
      before `ed83a19c`, and reproduced in review on the tree merged with
      `360b3ba0`. The suite does not hold it: leg d's own sentinel control is
      `R10-D6`'s, in `bin/sd_work.py`.

      **Leg d proves one clause of `R10-D4`, not the whole rule.** Its mutation
      defeats the `auth_mode` guard only. Three other ways to break the rule are
      held by `tests.test_sd_review_codex` and not by leg d. The first is the
      stored-key check in `codex_preflight`. The second is the
      `CODEX_METERED_ENV` scrub, which is in `child_environment` and not in the
      named checker. The third is the `codex_preflight` call in `review()`. In
      review, each of those three edits left the named test green and turned
      the whole module red. The row's subject keeps the whole rule, because
      that is what the rule is. The gap belongs to leg d's design of one
      mutation per row, and a row whose rule has several clauses inherits it.

      The table above was right that no import obstacle remained. It was wrong
      that nothing but a proof was needed. Leg a reads the *body* of the section
      a row names, and `section_body` drops the heading, so a heading that cites
      the id does not count as the section citing it. The row reddened leg a
      until the section's body cited `R10-D4` too. The id now sits in the
      section's teaching sentence, beside `codex_preflight`, and that sentence
      no longer credits `codex_preflight` with the environment scrub, which
      `child_environment` performs. Counting the heading would have changed
      leg a's measurement, so this slice did not make that change. `design.md`
      records it as a decision.

      **A finding about leg c's four dangling ids, measured on `239ff624`.**
      They are not undefined. Three of them carry a definition in a form
      `DEFINITION` cannot see, because that pattern requires a bold run
      *opening* with the id: `R5-D1` is written `**Obsidian vault stays
      system-of-record** (R5-D1)`, `R11-D1` sits in a table cell with no bold at
      all, and `R11-D30` is a heading. The fourth, `R11-D46`, is defined in no
      document in any form — its derivation was recorded as a comment in
      `tests/test_loc_caps.py`. Widening the grammar would move ids between two
      baselines at once and is a change to the measurement, so it is left for
      its own slice rather than folded into this one.
      **Decided 2026-09-14 (owner, note 1989):** that slice is the answer —
      one change widens `DEFINITION` and re-measures both leg c baselines
      together, rather than the four ids being repointed one at a time. It
      converts three false "dangling" entries into honest stranded ones.
      `R11-D46`, which is defined nowhere in any form, still needs its own
      answer and does not get one from the widening.
      Re-measured on `075eecf2`, 2026-09-14: the dangling set is unchanged at
      those same four ids.

      **Slice S2, 2026-09-16. `DANGLING_RULE_IDS` 4 → 0; `STRANDED_RULE_IDS`
      20 → 20, a different 20.** `source:tests/test_rule_registry.py::definitions_in`
      reads four forms now instead of one, and no prose was repointed. The
      three forms the finding above named were read off the archive on
      `2eafa78b`: the table cell at
      `docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md:251`
      for `R11-D1`, the heading at
      `docs/work/archive/2026-09/2026-09-04-host-parsing-refuses-what-it-cannot-parse/implement.md:12`
      for `R11-D30`, and the bold run closed before the parenthesised id at
      `docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md:206`
      for `R5-D1`. The fourth form is a bold run that *contains* the id, which
      is the team-lead decision of 2026-09-16, reversible by the owner: it
      makes the bold sentence at
      `docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first/implement.md:9`
      the definition of `R11-D46`, so the answer Dec-5 said that id still
      needed is this one, and the dangling set is empty. Two readings were
      narrowed before the sets settled, and each is held by a control in
      `source:tests/test_rule_registry.py::TheDefinitionGrammar`: a code span
      is blanked first, because this page quotes the archived `R5-D1` line
      inside backticks and read as prose that quotation defined the id live;
      and the heading and table forms read Markdown only, because a `#` line
      in `tests/test_loc_caps.py` is a comment, and reading it as a heading
      moved six stranded ids on the strength of citations. The stranded set
      gains the three ids above and loses three others the same grammar finds
      defined in a live file: `R10-D2` at `skills/sd-handoff/SKILL.md:123`,
      `R11-D4` at `CONTRIBUTING.md:204`, and `R11-D20` in the module docstring
      of `dashboard/now.py`, each in the closed-bold-then-parenthesis form
      the archived `R5-D1` uses. A grammar that reads the archive reads the
      live tree the same way, so those three are ids with a live definition
      and no row, which neither baseline measures. `R10-D2` no longer had a
      meter entry for the repeal Dec-4 decided; the repeal was owed until
      slice B, below.

      **Slice B, 2026-09-16. `R10-D2` is the first `repealed` row; both leg c
      baselines unchanged.** Re-measured on `fa7f870f` before the row was
      written: `R10-D2` is in neither `STRANDED_RULE_IDS` nor
      `DANGLING_RULE_IDS`, because S2's widened grammar reads its definition
      at `skills/sd-handoff/SKILL.md:123` (`**suppress the Copilot
      re-request** (R10-D2)`), so the fail-first the plan-pack brief named
      for this slice — leave the id in the stranded set and watch the
      baseline redden — was stale, and the tombstone invariant is the
      fail-first instead. `source:bin/sd_rules.py::STATES` allows `live` and
      `repealed` and nothing else; this is the first row to carry the
      second. The row holds `checker=None` and `proof=None`, and its
      `teaches` names the heading at `skills/sd-handoff/SKILL.md:118`, the
      section whose title says Lane B is not implemented. Fail-first: the row
      arrived with a checker string, and
      `test_every_live_rule_names_a_checker_that_exists` reddened with
      `R10-D2: repealed, but still holds checker='bin/sd-handoff::resolve_root'`;
      with `checker=None` the module passes, 30 tests. The invariant was
      widened in the same change to refuse a `proof` on a repealed row: a
      proof with no checker was already refused by the pairing check, but as
      a proof with no checker, which is true and is not the diagnosis.
      Mutations, each on a byte copy and restored by `diff -q`: a proof on the
      row reddens the invariant with `repealed, but still holds proof=...`;
      the row flipped to `live` reddens it with `live, but names no checker`.
      What no check holds: deleting the row. `R10-D2` is defined live, so it
      would leave no baseline entry behind — the "defined live, no row" gap
      S2 recorded, still an owner question on the item.

      **Slice D, 2026-09-16. `STRANDED_RULE_IDS` 20 → 19.** `R10-D1` is a
      row, per Dec-3 and after pack #995 moved the threshold out of the sweep
      module into `source:bin/sd_lib.py::DEFAULT_DAYS`. Re-measured on
      `74de42b1` first: `bin/sd-status` still carried the id in the `CLASSES`
      cell (`item activity + R10-D1`) and in the reason string (`past the
      {IDLE_DAYS}-day R10-D1 threshold`), and `skills/sd-status/SKILL.md:99`
      mirrored the cell. `second_list_entries` reads Python through `ast`, so
      a comment is invisible to it and an f-string's constant parts are data;
      both strings were rephrased to `idle threshold` and the id moved into a
      comment beside each, the way `R10-D5` cites itself in
      `bin/sd_setup_github.py`. The skill's cell changed with the string, and
      a sentence under the table cites `R10-D1` so leg a finds the id in the
      body of the section the row's `teaches` names, `One table enumerates
      the checks`. The row's checker is `bin/sd-status::_age_rows`, the
      producer that classifies `idle-planning`; its proof, run by leg d,
      replaces the `IDLE_DAYS` comparison with a condition that is never
      true, so every dated planning item is reported idle and
      `test_a_planning_item_past_the_threshold_ages_into_a_finding` reddens.
      Fail-first: the row was committed with the meter untouched, and
      `test_live_citations_resolving_only_into_the_archive_match_their_baseline`
      reddened, `FAILED (failures=1)`, the measured set being the baseline
      minus exactly `R10-D1`; with the id dropped the module passes, 33
      tests. A first draft of the skill sentence put `bin/sd-status` and
      `never` on a line with no id, and leg b's uncited-claims ratchet
      reddened on it; the sentence was rewrapped so the claim line cites the
      id. Mutations, each on a byte copy and restored by `diff -q`: the
      literal put back into the reason string reddens the second-list check
      naming `bin/sd-status` and the line; the sentence deleted from the
      skill section reddens leg a with `R10-D1: ... does not cite it`; the
      row's own proof applied by hand reddens the named test.

- [x] **5. Code rules, citing sd:430's checkers.** `tests/test_code_health.py`
      already enforces complexity, length, depth and clone floor. These become
      registry rows pointing at the existing checkers — no new enforcement, only
      registration. Verify: the ceilings in `tests/test_code_health.py` are
      unchanged by this step; `git diff` touches no ceiling constant.
      Read the ceilings off that file and not off the backbone item, which
      records a length ceiling of 80 where the file has
      `source:tests/test_code_health.py::LENGTH_CEILING` at 50; complexity and
      depth agree. A row written from the item body would register the wrong
      number.
      **Decided 2026-09-14 (owner, note 1989), for the two questions this step
      could not answer:** the ids come from a new round, `R12-D*`, allocated
      for registry-native rules, and `RULE_ID`'s grammar does not change — the
      registry stays the one place the grammar is written down. The teaching
      section is a new "code health" section in `skills/sd-check`, where
      `R10-D6` already teaches from, rather than a new skill or a widening of
      leg a to reach `CONTRIBUTING.md`. Widening leg a would have been a change
      to its measurement, which is not what this step is.
      **Step 5, 2026-09-16. `R12-D1` to `R12-D4` are rows; both leg c
      baselines unchanged; `tests/test_code_health.py` untouched.**
      Re-measured on `29de1970` first: the four ceilings stand at
      `source:tests/test_code_health.py::COMPLEXITY_CEILING` 20,
      `source:tests/test_code_health.py::LENGTH_CEILING` 50,
      `source:tests/test_code_health.py::DEPTH_CEILING` 5 and
      `source:tests/test_code_health.py::CLONE_FLOOR` 25, with `COMPLEX` at
      30 entries, `LONG` at 14, `DEEP` empty and `CLONES` at 5 pairs, and
      the registry held five rows. Each row is in the `R10-D6` shape, a test as
      checker, and its subject states the ceiling by name and by value —
      a reader at the row needs the number, and `bin/sd_rules.py` cannot
      import the module it lives in — so
      `test_a_code_health_subject_states_the_current_ceiling` in
      `source:tests/test_rule_registry.py::Registry` reads every
      `` `NAME`, N `` pair back off that module, and reads which names the
      subject may state off the checker's own body, so a true sentence
      about the wrong ceiling fails (Copilot's finding on #1008); it
      selects rows by the checker's file, not by id. The skill section is `Code health` in
      `skills/sd-check/SKILL.md`, four bullets each opening with an id, the
      number stated nowhere in it. The proofs violate the rule in a tracked
      file rather than lowering a ceiling, which would prove only that the
      test reads its constant: each replaces the first `def` line of
      `bin/sd_library_guard.py`, the smallest module in the corpus, with a
      violating function and then that line again, and the violation is
      built from the constant — `COMPLEXITY_CEILING` `if` statements score
      one over, `LENGTH_CEILING + 1` statements, `DEPTH_CEILING + 1` nested
      `if`s, two functions of one body past `CLONE_FLOOR` — so a raised
      ceiling moves the violation with it. What the re-measurement found
      that the plan had not: the code-health checkers enumerate their corpus
      with `git ls-files`, and leg d's copy carried no index, so the named
      test raised `CalledProcessError` and ran nothing — which
      `enforcement_error` refused, correctly, as evidence of anything. The
      copy now gets `git init` and one `git add` of what was copied
      (`source:tests/test_rule_registry.py::copy_tracked`); the index lists
      paths, so a mutated file stays in the corpus. Fail-first: the rows
      were committed with no `MUTATIONS` entries and
      `test_every_live_checker_carries_a_mutation` reddened, `FAILED
      (failures=1)`, naming all four checker locations; with the entries the
      module passes, 34 tests. Mutations, each on a byte copy and restored
      by `diff -q`: the length proof applied by hand reddens
      `test_no_function_is_longer_than_the_ceiling` with
      `bin/sd_library_guard.py::_leg_d_too_long: 51`; `R12-D2` deleted from
      the skill section reddens leg a with `R12-D2: ... does not cite it`;
      the complexity subject's 20 changed to 21 reddens the agreement test,
      which reports the subject stating `COMPLEXITY_CEILING` as 21 where
      `tests/test_code_health.py` has 20; one entry's `old` changed to text
      the file does not hold reddens leg d with `Found 0 occurrences`.
      Timing is in `design.md`'s leg d decision: one copy per run still
      holds, and the whole module went from 9.70 s for 33 tests to 38.88 s
      for 34, because `TheSharedCopy` runs the leg a second time in-process.

- [x] **6. Prose rules, in their narrowed forms.** Rule 2 as filed. Rules 1 and
      3 as narrowed in `design.md`, each with its baseline. Verify: each rule
      reddens under mutation; no rule's first run reddens the existing corpus.
      **Step 6, 2026-09-16. `R13-D1` to `R13-D3` are rows on a round of
      their own, each a per-document baseline that only falls; both leg c
      baselines unchanged; nothing in the corpus was swept.** All three
      teach from one new section, `Prose rules` in `skills/sd-check/SKILL.md`,
      beside the code rules, and all three proofs edit that page in leg d's
      copy. Re-measured on `ef7c0c7b` first, and one premise did not hold:
      the plan had rule 1's checker reading the `compared` rows, on the
      strength of the census table in `design.md` (54 on `e6c2cb20`), but
      since sd:525 a live anchored `path:line` into code is
      `anchored-line-into-code`, red and empty, so `compared` held one row
      and it was archived. The population the narrowed rule is about is the
      *unanchored* citation -- `no-adjacent-anchor`, `separator-not-adjacent`,
      `anchor-not-a-symbol` -- which the gate opens only to check the line is
      in range. `R13-D1`'s checker is
      `test_line_citations_into_a_symbol_match_their_baseline` in
      `tests/test_doc_citations.py`, over
      `source:tests/test_doc_citations.py::symbol_anchored_citations`: the
      rows of `classify` whose document is live, whose target is a Python
      file inside the checkout, and whose line
      `source:tests/test_doc_citations.py::enclosing_declaration` places
      inside a `def` or a `class` at the two levels the `source:` form can
      name. The baseline is `SYMBOL_ANCHORED_CITATIONS`, 145 rows in 17
      documents on `ef7c0c7b`, 107 of them in one item's `prd.md` and
      `implement.md`. Exempt: a line outside every symbol, a `quoted` row, a
      markdown target, a target outside the checkout (one, in an absolute
      path a dashboard page cites) and a file that does not parse. `R13-D2`'s
      checker is `test_present_tense_counts_match_their_baseline` in the new
      `tests/test_prose_counts.py`, over
      `source:tests/test_prose_counts.py::present_tense_counts`; a module
      rather than a `bin/sd-docs-lint` rule, because measured on `ef7c0c7b`
      the linter's tree rules read `docs/work` only and rule 7 opens the
      rest of the markdown for `docs/work/` references alone, so no page
      the rule is about was read for its prose there. The corpus is every
      markdown file under `skills/`, `README.md`, `AGENTS.md`, `docs/spec`
      and `.claude/rules`, 54 files; the predicate is `<number> <noun>` on
      one line with the noun from `ENUMERABLE`, outside a fence or a code
      span, and the line carrying no commit, `#<n>` number or `YYYY-MM-DD`
      date. Population on `ef7c0c7b`: 2 lines, both violations, held in
      `PRESENT_TENSE_COUNTS` -- one a test's coverage points in a spec
      page, one `surfaces` read as a verb in `sd-status`'s skill -- so the
      rule's first run reddened nothing and the design's exemption for a
      measurement is what keeps every other count out. A wider noun set was
      measured and left: `lines`, `rows` and `scripts` name thresholds and
      measurements in this corpus and nothing enumerable. `R13-D3` registers
      leg b as it stands: the checker is
      `test_uncited_tool_behaviour_claims_match_their_baseline`, the
      predicate `source:tests/test_rule_registry.py::claims_in`, the baseline
      `UNCITED_SKILL_CLAIMS`, and the row's comment says nothing new is
      enforced. Fail-first: the rows and their `MUTATIONS` entries were
      committed first and the module reddened `FAILED (failures=8)` -- leg a
      on the missing section, the checker-resolution test on three checkers
      that did not exist, leg d on three mutations that edited nothing; with
      the checkers and the section the module passes, 35 tests. Mutations,
      each on a byte copy and restored by `diff -q`: each baseline raised by
      one reddens its own test; each row's proof applied by hand reddens the
      test its row names; `R13-D2`'s bullet deleted from the section reddens
      leg a with `R13-D2: ... does not cite it`;
      `enclosing_declaration` made to answer `None` reddens four tests in
      `TheSymbolPreference`; the measurement exemption dropped reddens the
      predicate test on all four marks. Leg d's child budget rose by three
      rows and `LegD` read real 9.82 s for 9 tests at load average 6.14,
      under the 21 s Dec-6 budgets.

- [x] **7. The pre-commit tier.** **Every timing this step used to state has
      expired, and the shape of the step is now open rather than settled.** It
      read that the code checkers run whole at 1.71 s, that only
      `bin/sd-docs-lint` at 19.87 s is diff-scoped, and that the two whole-tree
      passes come to 2.55 s before any hook overhead. Those three numbers were
      measured against `e6c2cb20` and none of them reproduces: `design.md`
      carries what re-measurement found and why it is a signal rather than a
      new record. What survives is the argument, not the arithmetic — a hook
      slow enough to be bypassed is an advisory rule in the costume of an
      enforced one, and no threshold is set here on purpose.
      **Decided 2026-09-14 (owner, note 1989):** this step re-runs the timings
      inside its own pull request and re-makes the diff-scoping decision there,
      as `design.md`'s own reversal clause instructs, rather than inheriting
      either the expired numbers or the spot checks that retired them. The
      pre-commit tier is not dropped for CI alone.
      Verify, unchanged in shape: time the assembled hook on a one-file diff,
      record the number, and set the budget from that result in the same pull
      request; re-run the three whole-tree timings there too, on a machine
      whose load is stated, and write them down beside their commit.
      **Landed 2026-09-16.** The nine readings, at `ef7c0c7b`, three runs
      each, `/usr/bin/time -p` real seconds with the one-minute load average
      beside each, before any hook existed: `tests.test_code_health` 1.79 /
      1.71 / 1.74 at load 9.90 / 8.73 / 7.39; `tests.test_doc_citations`
      3.41 / 3.38 / 3.33 at 9.91 / 8.75 / 7.39; `bin/sd-docs-lint` 20.34 /
      21.85 / 21.65 at 9.91 / 8.75 / 7.52, of which 2.0 s is CPU and the rest
      is seventy `git fetch` and `git ls-remote` children under
      `sd_lib.delivered` in rule 2, so the tool's wall time is git
      subprocess calls reaching the network, not its own reading of the
      corpus. The hook is `hooks/pre-commit`,
      Python (a tracked shell file outside `.github/scripts/` reddens
      `tests/test_no_shipped_shell.py`), run on the staged files: `SD_SKIP_HOOKS=1`
      skips it with a one-line notice; otherwise a refusal by name of any
      staged path whose working-tree copy differs from the index, since both
      gates read the working tree and the commit holds the index (the first
      review round's finding: a bad file staged and then fixed without
      restaging passed while the commit still carried the bad blob), then
      Ruff over the staged Python, then `tests.test_code_health` and
      `tests.test_doc_citations` whole, the first red exiting with that
      tool's output and status, and its own wall time printed on exit
      against the budget. The assembled hook on a
      one-file diff read 5.26 / 5.07 / 5.01 s at load 7.47 / 7.60 / 7.55. The
      budget is 8 s, in the header and in `BUDGET_SECONDS`. The decision:
      both test passes run whole, since `select-tests.py` puts both in
      `ALWAYS_RUN` and neither has a diff-scoped form; `bin/sd-docs-lint` is
      not in the hook, since `--changed` needs `--pr-body` and scopes rule 8
      only and the tool's wall time is network; Ruff is file-scoped by nature.
      `make hooks` installs it as the relative link `<common .git>/hooks/
      pre-commit -> ../../hooks/pre-commit`, one per clone, read from the
      main checkout and shared by every linked worktree, prints the path,
      refuses by name to replace anything else there, refuses to run while
      a `core.hooksPath` is set (`--git-path hooks` would honour it), and
      never sets one: the directory is `hooks/`, not `.githooks/`, because
      `bin/sd-status` reports `.githooks` and a set `core.hooksPath` as the
      retired gate stack's residue with a removal command, and the pack's own
      hook must not match its own detector (`design.md`, the re-made
      decision). `bin/sd_install.py` is not edited, and folding the hook into
      `--user` is the owner's call. `tests/test_pre_commit_hook.py`,
      fail-first (`FAILED (failures=5)` with no hook, then `OK`; the layout
      cases `FAILED (failures=8)` before the move, then `OK`): the file is
      tracked at `hooks/pre-commit`, executable and states the budget once,
      equal to `BUDGET_SECONDS` and to `design.md`; both named passes exist
      in this checkout; in a throwaway repository a staged `import os` exits
      non-zero naming `bad.py`, `SD_SKIP_HOOKS=1` exits 0 with the notice,
      and a clean file exits 0 printing the wall time; a staged file fixed
      in the working tree but not restaged is refused naming it, with Ruff
      not run; with the two modules present as stubs the hook runs them
      (`Ran 2 tests`), a red stub fails the commit with status 1, and a
      staged `git rm` of one stub is refused naming the module (a deletion
      is not a staged path, so only the module check sees it); a python
      shebang past 128 bytes and a capped unterminated one are both sent to
      Ruff while a long shell shebang is not, the bound being code health's
      4096; without `.venv` and with a `python3` shim first on `PATH`, Ruff
      and the passes both run;
      `make hooks` over a
      copy of the `Makefile` makes the relative link and passes again over
      its own link, refuses a stranger file and leaves it, refuses while
      `core.hooksPath` is set and makes no link, a `git commit` of
      a staged `import os` fails through the link with no commit landing,
      and from a linked worktree the link lands in the main `.git/hooks`
      with the same relative target and reads the main checkout's file,
      and afterwards
      `residue_section` from `bin/sd-status` reports neither `githooks` nor
      `hooks-path`. Mutations, each restored from a byte copy: the Ruff step
      removed reddens the Ruff case; the skip branch removed reddens the
      escape-hatch case; `chmod -x` reddens the file case; the recipe also
      setting `core.hooksPath` reddens the residue case with `'hooks-path'
      unexpectedly found`; the refusal removed reddens the stranger case;
      the `unittest` call replaced by `status = 0` reddens both stub cases;
      the divergence guard emptied reddens the not-restaged case with
      `0 == 0 : All checks passed!`; the link target misspelt reddens the
      commit case with `the commit went through` and the link case with
      `FileNotFoundError`; the common dir replaced by `--git-dir` reddens
      the worktree case; the absent-pass failure downgraded to a notice
      reddens the deletion case; `SHEBANG_LIMIT` at 128 reddens the shell
      case with `EXE001`; the fail-closed return removed reddens the capped
      case; the fallback renamed reddens the `python3` case with
      `FileNotFoundError`; the budget header duplicated reddens the file
      case with `2 != 1`; the `core.hooksPath` refusal removed reddens its
      case with `git hooks: .githooks/pre-commit -> ...`.

- [ ] **8. The authoring tier.** Skills consult the registry and name the rule
      ids in scope. Filed last, because it depends on the registry carrying
      rules.
      **Decided 2026-09-14 (owner, note 1989): it runs next, ahead of the rest
      of step 4.** The ordering above assumed the backfill could proceed
      without it. It cannot: 17 of the 20 stranded ids are taught by no skill
      section, so leg a blocks every one of them until a section exists to
      teach it, and the alternative — backfilling only the 3 taught ids —
      exhausts in a single slice. Step 8 is the constraint on step 4, not its
      consequence.

Steps 1 to 3 are the deliverable, and all three are done: `bb379027` (#882)
landed them and `d745474b` (#889) corrected leg b's baseline. Steps 4 to 8 are
payload and may be batched into fewer pull requests to reduce CI churn; step 4
is partially delivered, in three slices recorded above, and step 8 now precedes
the rest of it.

## Verification

**Named before the work starts.**

- Every meta-check leg is proved by mutation, not by passing: remove the guard,
  confirm a *named* test goes red, restore, and `diff -q` must report the tree
  identical. A mutation script asserts its own edit applied — `assert
  t.count(old) == 1` — because a script whose pattern matches nothing reports a
  false pass. That has happened twice on this repository in one week.
- **Leg d is that protocol executed by the suite rather than by a person**, once
  per live row with a checker, and it is held to the same bar it applies: the
  edit-landed count, the green control run, the red mutated run, and the
  restoration are four separate assertions, and a sentinel edit that violates
  nothing must leave the same test green. A leg that reports red for a child it
  could not start would otherwise read as every checker enforcing.
- A fixture must be checked for vacuity. A test that exercises a guard through
  several layers can fail earlier, for the wrong reason, and still pass. Where a
  guard can be called directly, call it directly, and include a control
  asserting the case that *should* succeed.
- Baselines: `pytest` the baseline test with the number raised by one; it must
  go red. A baseline that does not redden when raised is not a ratchet.
- Leg c's dangling set is empty: `DANGLING_RULE_IDS` is `frozenset()` since
  S2 (`fa7f870f`), because `source:tests/test_rule_registry.py::definitions_in`
  reads every form the corpus writes a definition in. The first run, on
  `cddd3b98`, named exactly the four ids the one-form grammar could not see,
  and that measurement is recorded under step 4; it is no longer the
  criterion. The criterion now is that the set stays empty: a new id in it
  means live prose cites a rule no document defines and no row carries.
- Full suite through the repository's own runner: `make test`, which runs
  `.github/scripts/run-tests.sh` and shards `python -m unittest` across workers.
  That is the authoritative suite and the one CI gates on. A focused run is
  `python -m unittest tests.test_<module> -v`.
  `pytest` is a convenience here, not the contract: under `pytest tests/` this
  tree reports 19 collection errors from a missing `sd_db` module, pre-existing
  on `origin/main`, which is a fact about `pytest` rather than a baseline for
  this project.
- `bin/sd-docs-lint` exits 0.

**What cannot be verified here.** Whether an R-id in an archived design document
is a live rule or a historical decision is a judgement, not a check. Step 4
records the decision per id in the registry row; nothing can test that the
judgement was right.

**Log 2026-09-16, slice C (leg d, Dec-6).** `LegD` timed with one command
each on this machine, `/usr/bin/time -p .venv/bin/python -m unittest
tests.test_rule_registry.LegD`: before, on `b4211959`, real 6.81 s for 8 tests
at load average 39.25; after, real 2.72 s for 9 tests at load average 32.26.
The loads differ, so no ratio is claimed; the copy itself measured 2.16 s for
1306 tracked files, once per run now instead of once per row or control.

## Log

- 2026-09-16 step 8, first slice: the authoring tier is `bin/sd-rules --for
  <path>`, by the owner decision of 2026-09-16 (option (a), a read verb that
  prints the live rows whose scope matches the file being written, id,
  subject and teaching section, called from a skill's setup step). Built as
  a standalone command rather than an `sd rules` verb because `bin/sd` was
  held by another lane that day; the alias is its own slice. The scope rule is
  `points_into_code`'s, markdown is prose and everything else is code, bound
  by test. `skills/sd-handoff/SKILL.md`, the skill that teaches the most
  stranded ids (2 of 20 on `2eafa78b`, `sd-status` 1, no other skill any;
  on `fa7f870f`, after #993 widened the definition grammar, 1 and 1), names
  the verb in its restore step. Step 4 is untouched here.
- 2026-09-16 step 4, slice D (R10-D1, Dec-3): `STRANDED_RULE_IDS` 20 → 19.
  `bin/sd-status` cites `R10-D1` from two comments and carries it in no
  string; the row's checker is `bin/sd-status::_age_rows` and leg d runs its
  proof.
- 2026-09-16 step 5 (Dec-1, Dec-2): `R12-D1` to `R12-D4` register the four
  code-health checkers with no enforcement change; `tests/test_code_health.py`
  is untouched. Leg d's copy carries an index now, because those checkers
  enumerate by `git ls-files`, and the four proofs run under it.
- 2026-09-16 step 5 residue (sd:971): leg d runs every row's control in
  one child and one mutated child per row, 20 children → 13 on eight rows
  and two controls; `LegD` real 14.71 s at load 6.31 → 10.34 s at 6.28,
  budgeted at 21 s in `design.md`, Dec-6.
- 2026-09-16 step 6: `R13-D1` to `R13-D3` register the three prose rules in
  their narrowed forms, each a per-document baseline that only falls --
  `SYMBOL_ANCHORED_CITATIONS` in `tests/test_doc_citations.py`,
  `PRESENT_TENSE_COUNTS` in the new `tests/test_prose_counts.py`, and leg
  b's `UNCITED_SKILL_CLAIMS` as it stood -- taught from `Prose rules` in
  `skills/sd-check/SKILL.md`; `LegD` real 9.82 s at load 6.14.
- 2026-09-16 step 7 (Dec-7): `hooks/pre-commit` runs Ruff on the staged
  Python and the two whole-tree test passes, read 5.01–5.26 s on a one-file
  diff at load 7.47–7.60, budgeted at 8 s; `bin/sd-docs-lint` stays out of
  the hook, its 20 s being seventy git network children; `make hooks` links
  it from `.git/hooks`, not `.githooks/` and not `core.hooksPath`, which
  `bin/sd-status` reports as residue. The diff-scoping decision is re-made
  in `design.md` on those readings.
