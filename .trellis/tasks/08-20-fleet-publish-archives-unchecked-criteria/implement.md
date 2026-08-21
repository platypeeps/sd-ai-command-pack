# Implementation plan

Ordered. Each step names the command that decides whether it worked. A step
whose check fails is not "mostly done" — stop and fix before advancing.

## 1. Criteria parser and tag grammar

Add to `scripts/sd-ai-command-pack-fleet-publish.py`:

- `parse_acceptance_criteria(text)` — returns one record per `- [ ]` / `- [x]`
  line under the `## Acceptance Criteria` heading: line index, current tick
  state, tag id, tag attributes, prose.
- Recognize `<!-- verify: <id> [k=v ...] -->`. Tolerate absent tags (untagged is
  a valid, unverifiable criterion, not a parse error).
- Stop at the next `##` heading. The refresh PRD carries a `## Post-archive
  handoff` section directly after the criteria, and swallowing it would put
  the disposition block in the wrong place.
- A `prd.md` with no `## Acceptance Criteria` heading is a no-op that reports
  the absence, not an error. A lightweight consumer task is allowed not to have
  one, and a crash here would fail a publish over a section that was never
  required.

Check: `.venv/bin/python -m unittest tests.test_fleet_publish -k criteria`

## 2. Verifier registry

- `install-audit` — resolve the install-audit helper beside this script, the
  same pattern the record-session wrapper and review preflight already use. Run
  it with `--repo <consumer>` plus one `--expected-platform` per platform named
  in the tag. Verified on exit 0 **and** the reported provenance matching the
  tag's `release=`. The expected release and platform set must come from the
  tag: publish takes no release argument, so a verifier that only checks the
  exit code would tick "provenance is at 0.71.39" having confirmed nothing about
  the version.
- `tracked-mode` — `git ls-files -s <path>` in the consumer worktree; verified
  when the mode equals the tag's `mode=` attribute (default `100755`).
- `bundle-shape` — verified when publish reached the tick step, which is
  reachable only after `work_commit()` succeeded and the precondition gate
  passed.
- `lane-evidence` — resolved from `--criterion-evidence`, never computed.
- Unknown id: unverified, with the id named in the note. Never a tick.

Check: `.venv/bin/python -m unittest tests.test_fleet_publish -k verifier`

## 3. Wire into the publish flow

- New repeatable arg `--criterion-evidence <id>=<verified|unverified>[:<note>]`.
  Reject a malformed value at parse time, not at use time.
- Call `tick_acceptance_criteria()` from `archive_and_journal()` **immediately
  before** the `task.py archive` invocation. Not before `work_commit()`, not
  after the archive commit — `design.md` records why both are wrong.
- Rewrite `prd.md` in place: flip proven boxes to `- [x]`, leave the rest, and
  write the generated disposition block below the criteria list.
- Make the rewrite idempotent. Delimit the block with stable start/end markers
  and replace it when present rather than appending. Publish aborts loudly with
  no rollback if `task.py archive` fails, and the tick runs *before* that call —
  so a retry from a repaired tree re-enters with the boxes already flipped and a
  block already on disk. Append-only would stack a second block per attempt.
  Re-ticking an already-ticked box must be a no-op, not a duplicated marker.
- Return the unticked set out through `publish()` into the result JSON as
  `uncheckedCriteria`.

Check: `.venv/bin/python -m unittest tests.test_fleet_publish` — full module green,
no pre-existing test regressed.

The suite is `unittest` run through `.github/scripts/run-tests.sh`, not pytest;
`-k` is unittest's own filter and matches method names.

## 4. Regression coverage

The PRD requires both halves proven. Minimum set:

- a tagged, satisfiable criterion is ticked in the archive commit;
- a tagged criterion whose verifier reports unverified stays `- [ ]` and appears
  in the disposition block;
- an untagged criterion stays `- [ ]` and is named;
- an unknown tag id stays `- [ ]` and is named — the anti-guessing rule;
- a `lane-evidence` criterion with no matching flag stays `- [ ]`;
- a second `tick_acceptance_criteria()` pass over its own output changes
  nothing — same ticks, one block;
- a `prd.md` with no criteria heading publishes unchanged;
- the tick lands in the archive commit and `assert_trellis_only_delta()` still
  passes.

Follow the file's existing shape: `unittest` classes, not bare functions. The
ordering test must run `publish()` end to end and assert against the committed
tree — a test that calls `tick_acceptance_criteria()` directly cannot catch a
regression that moves the call site, which is the failure this design is most
exposed to.

Check: the six cases above exist and pass; `git show --stat` on the archive
commit in the end-to-end test shows `prd.md` inside it.

## 5. Refresh skill emits tags

- Edit `templates/.agents/skills/sd-fleet-refresh/SKILL.md` — the source. Add
  the tag grammar to the PRD-authoring guidance at the `checkout-validation`
  stage, where the seeded task is created.
- Document `--criterion-evidence` and which lane stages produce the evidence for
  the two criteria that need it.
- Sync the one full copy: `.agents/skills/sd-fleet-refresh/SKILL.md` is the
  source minus its `model: sonnet` frontmatter line. `make generate` and
  `make sync` do **not** cover it — this skill is absent from the install
  manifest, so no installer target owns the copy. The command and prompt
  surfaces are wrappers that do not embed the body.

Check: `.github/scripts/check-command-surface-drift.py` clean,
`make surface-check` clean, and
`diff <(grep -v '^model: sonnet$' templates/.agents/skills/sd-fleet-refresh/SKILL.md) .agents/skills/sd-fleet-refresh/SKILL.md`
empty. The drift checker passing is *not* evidence the copy is current — it was
clean while the copy was still stale, which is why the explicit diff is the
check that decides this step.

## 6. Spec

New rule under `.trellis/spec/tooling/`: where the tick lands and why the
ordering is fixed, the anti-guessing rule, and the fail-closed set. Cite the
establishing task by its **archive** path — `.trellis/spec/tooling/fleet-publish-generated-content.md`
records that a spec citing a live task path breaks the documentation
path-reference gate in the same finalization that publishes it.

Check: `node scripts/sd-ai-command-pack-review-preflight.mjs` with no arguments
(whole-tree scan) reports zero FAILs. Passing `--base` silently scans nothing.

## 7. The two already-merged consumers

Per `design.md`, recommended disposition is annotate-not-tick, and this is the
one item to settle at the review gate before acting. If confirmed: one dated
line appended to each archived PRD in anomaly-metric-creator and hoa-manager
naming this task. Two small PRs, no pack change.

Check: PRD acceptance criterion four is only satisfiable once the choice is
written back into `prd.md`. Record the decision there whichever way it goes.

## Review gates

- After step 4 — the mechanism is testable in isolation and this is the last
  cheap point to change the tag grammar.
- After step 6, before step 7 — step 7 touches two consumer repositories and is
  the only step with a blast radius outside the pack.

## Rollback

Steps 1 through 4 are one file plus its tests: `git revert` of the work commit
restores the prior behaviour with no migration, because an untagged PRD is
valid input and produces today's outcome — everything unticked, now with a
disposition block explaining it.

Step 5 is regenerated content; re-running `make generate` and `make sync` after
a source revert restores every copy.

Step 7 is append-only text in two archives and is revertible per repository.

## Full gate before finish

`make check`.
