# Implement — adoption diffs do not require a hand-written scope section

Ordered checklist for `design.md`. Red-first: every test below is written and
observed failing against current `main` before the script changes.

## 0. Baseline

- [ ] `python3 -m pytest tests/test_review_scope.py -q` green on a clean tree.
      Record the count; 53 `test_` functions exist today and the number must not
      drop.
- [ ] Confirm the defect repro from `prd.md` still fails at exit 1 in a consumer
      checkout. If it now passes, stop — the premise moved.

## 1. Tests first (all red)

Add to `tests/test_review_scope.py`, reusing `make_scoped_advisory_repo` and
`run_advisory_scope` where they fit; enforcing-mode cases need a sibling helper
that does not pin `SD_AI_COMMAND_PACK_SCOPE_CHECK=advisory`.

- [ ] `test_adoption_diff_of_manifest_and_provenance_needs_no_section`
      — exactly `.sd-ai-command-pack/manifest.json` + `provenance.json`,
      marker-free body, enforcing mode, expect exit 0 and no `error:` line.
- [ ] `test_adoption_diff_covering_a_pack_file_outside_the_pack_dir_is_exempt`
      — add `.prism/rules.schema.json`, the path `99d8843` exercises. Pins that
      the exemption follows the receipt, not the `case` fast path.
- [ ] `test_installed_targets_itself_may_change_in_an_adoption_diff`
      — `install.py` rewrites it when the target set changes.
- [ ] `test_one_authored_file_alongside_pack_files_still_requires_a_section`
      — requirement 2. Expect exit 1.
- [ ] `test_appending_an_authored_path_to_the_receipt_does_not_exempt_it`
      — the receipt-in-diff hazard: diff appends `src/authored.py` to
      `installed-targets.txt` *and* changes `src/authored.py`. Expect exit 1,
      because ownership is read from the base copy. **This is the security
      criterion; it must fail loudly against a head-copy implementation.**
- [ ] Fail-closed, four cases, each expect exit 1 on an otherwise-exempt diff:
      base ref unresolvable; base receipt absent; base receipt unreadable; base
      receipt empty/whitespace-only.
- [ ] `test_repomix_only_diff_is_not_treated_as_adoption`
      — pins the rejected alternative in `design.md`: `docs/repomix-map.md`
      alone is all-*scoped* but not pack-owned, so it must still require a
      section.
- [ ] `test_untracked_file_does_not_defeat_the_adoption_exemption`
      — an all-pack-owned diff plus one untracked scratch file still exits 0.
      Pins that the predicate uses tracked changes only; fails against a
      `collect_changed_files`-based implementation.
- [ ] `test_explicit_targets_file_override_is_honoured_over_the_base_copy`
      — with `SD_AI_COMMAND_PACK_TARGETS_FILE` set, the override governs and the
      base-copy substitution is skipped. Guards the nine existing call sites in
      `tests/test_review_layout.py` and `tests/test_review_scope.py`.
- [ ] `test_adoption_diff_emits_no_scope_advisory_marker`
      — advisory mode, all-pack-owned diff: stdout must not contain
      `sd-ai-command-pack-scope-advisory:`. This is `rwbp-website`'s lane.
- [ ] Run the suite; confirm every new test fails and no existing test does.

## 2. Implement

- [ ] Add `tracked_changed_files()` — `collect_changed_files` without the
      trailing `git ls-files --others --exclude-standard` (`:112`). Leave
      `collect_changed_files` itself untouched; classification keeps its
      current input set.
- [ ] Add `base_targets_file()` — materialize
      `git show "${base_ref}:.sd-ai-command-pack/installed-targets.txt"` to a
      temp file, `trap`-cleaned. Non-zero exit, empty output, or unresolvable
      base ref all return non-zero.
- [ ] Add `is_adoption_only_diff()` per `design.md`, calling
      `is_pack_target_path` with `TARGETS_FILE` bound to the base copy for the
      duration of the sweep only, and **only when
      `SD_AI_COMMAND_PACK_TARGETS_FILE` is unset**. When it is set, the override
      governs unchanged.
- [ ] Insert the early return in the classification loop **before** the advisory
      branch (`:449`) and before `check_pr_body_scope` (`:482`), printing the
      `info:` line from `design.md`.
- [ ] Leave `is_pack_target_path` and `check_pr_body_scope` signatures
      unchanged.

## 3. Validate

- [ ] `python3 -m pytest tests/test_review_scope.py -q` — all green, count ≥ 53
      plus the new tests.
- [ ] `python3 -m pytest tests/test_pr_body_scope.py tests/test_bookkeeping_ci_scope.py -q`
      — the two sibling suites that exercise the same script.
- [ ] `.github/scripts/run-tests.sh` — full suite, 0 failures.
- [ ] `shellcheck scripts/sd-ai-command-pack-review-scope.sh` clean.

## 4. Requirement 3 — template wording

- [ ] `templates/.github/PULL_REQUEST_TEMPLATE.md:6` and
      `templates/.github/copilot-instructions.sd-ai-command-pack.md:61` gain a
      clause naming the exemption.
- [ ] Grep for other copies of that wording before editing; the pack ships
      mirrored templates and a stale twin is the expected failure here:
      `grep -rn "tooling/generated" templates/ plugins/ docs/`.

## 5. Ship

- [ ] Version bump in `manifest.json` + CHANGELOG entry. **Read `main`'s current
      version at that moment** — two sessions have been landing bumps and a
      collision on this repo has already happened once (#551 vs #549).
- [ ] `make sync` → `make generate` → `sd-ai-command-pack-fleet-candidate-check.py`
      → `make check`. This order; it is the one that converges.
- [ ] Confirm all four copies of the script are hash-identical.
- [ ] PR. No admin override, no `--force` against a consumer.

## 6. External evidence

- [ ] Rerun the `prd.md` repro unchanged in a consumer checkout on an
      adoption-shaped diff: exit `0`, no `error:` line. Assert from outside the
      pack, as the PRD requires.
- [ ] Confirm the machine layer carries the shipped version before treating the
      replay as evidence — `~/.agents/bin` was found stale during this task's
      own session, and receipt reuse keys on target identity, so pass
      `--no-reuse`.

## Rollback

Revert the commit. The predicate is additive and unreferenced elsewhere; no
receipt format changes and no state is written.
