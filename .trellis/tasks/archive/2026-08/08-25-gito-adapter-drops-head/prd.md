# Local stage gito adapter drops the head ref

The local stage resolves a review target as a `(base, head)` pair and records
both in the receipt, but the gito adapter only ever transmits the base. gito
supplies its own head from the working tree, so the range actually reviewed is
`base..<whatever is checked out>` rather than `base..head`.

## Evidence

`templates/scripts/sd-ai-command-pack-review-local.py`, in `_expand_argv`
(an earlier draft of this PRD called it `_provider_argv`; no such symbol
exists), builds the delta invocation as:

```python
elif provider.adapter == "gito":
    output = str(attempt_dir / "provider-output")
    if scope == "codebase":
        result = ["gito", "review", "--all", "--path", str(repo), "--out", output]
    else:
        result = ["gito", "review", "--vs", str(target["base"]), "--out", output]
```

`target["head"]` is in scope at that point — the `argv` adapter branch directly
below substitutes it as `{head}` — and is simply not passed.

Note the `else` covers two canonical scopes, not one: `CANONICAL_SCOPES` is
`{"worktree", "branch_delta", "codebase"}`, and only `branch_delta` is wrong.
For `worktree` (from `--scope changes`) the subject of review *is* the
uncommitted tree, so comparing the index against the base is correct there.

gito's own CLI documents both halves of the range:

```
refs   [REFS]  Git refs to review, .. (e.g. 'HEAD..HEAD~1'). If omitted, the
               current index (including added but not committed files) will be
               compared to the repository's main branch.
--what   -w    TEXT  Git ref to review
--against,--vs TEXT  Git ref to compare against
```

So `--what` is the missing argument, and its default is what silently supplies
the wrong head.

## How it was found

Observed 2026-08-25 while replaying `sd-github-review` PR #70
(`c3ec5f64...2880186`) for criterion 6 of that repository's
`08-09-review-gate-advisory-convergence`. The stage was invoked with
`--scope pr --base c3ec5f64 --head 2880186` from a working tree at `main`.

The receipt recorded the correct target — `remoteSummary.base` `c3ec5f64…`,
`familyGate.exactHead` `2880186…` — while gito reviewed `c3ec5f64..main`.
**Fourteen of the fifteen findings cited files that are not in the 23-file PR #70
diff at all**, several in paths created months after that head — among them
`docs/RELEASE_CHECKLIST.md` [absent: consumer repo, not this one] and
`.trellis/tasks/08-09-review-gate-advisory-convergence/design.md` [absent: consumer repo, not this one].
Only one finding fell inside the range.

Rerunning the identical command from a detached worktree whose tree *was* the
head returned 5 findings, all in range — matching the shape the consumer's PRD
records for its earlier gito replay of the same range.

gito states the mechanism in its own log line, captured in the receipt's
`attempts[].diagnostic`:

```
INFO: Making merge-base diff: INDEX vs d4e08e7d469c943ec66dad0792d6365679cf97cd
```

`INDEX` is the working tree. The base is the only ref it was given, and the
other side of the comparison is whatever happens to be checked out — so the
defect is observable from the provider's output without inspecting the argv.

## Why it matters

The failure is silent and severity-free: the stage exits normally, the receipt
carries the right base and head, and the finding count looks plausible. Nothing
distinguishes "reviewed the requested range" from "reviewed a different one".

In ordinary use the working tree *is* the head, so the bug is invisible. It bites
exactly when the head is supplied explicitly and differs from the checkout —
replays of a historical range, any caller reviewing a ref it has not checked out,
and any future non-worktree invocation. The receipt's own `contentDigest` and
`exactHead` become claims the provider output does not support.

This is the same class as the four provider defects catalogued in the consumer's
PRD: exit zero, a finding count printed, and nothing telling the caller what was
actually looked at.

## Requirements

1. The gito delta invocation transmits the resolved head as well as the base.
2. A receipt whose plan names a head cannot be satisfied by provider output taken
   against a different head — either the head reaches the provider, or the stage
   refuses.
3. The `codebase` and `worktree` scopes keep their current behaviour. Only
   `branch_delta` is wrong. "The delta branch" in the code is one `else`
   covering both `worktree` and `branch_delta`, so a fix keyed off "not
   codebase" would break `worktree`.

## Acceptance criteria

- [x] `_expand_argv` passes the resolved head to gito for `branch_delta`,
      asserted by a test on the constructed argv that fails against today's code.
      — `test_gito_branch_delta_argv_carries_head_and_base_in_order`. Confirmed
      red before the change: `'--what' not found in ['gito', 'review', '--vs',
      '<base>', '--out', ...]`.
- [x] The same test pins the base argument, so a fix that swaps the two —
      reviewing `head..base` — fails rather than passing on argv length alone.
      — asserts both values by position and asserts `--what` precedes `--vs`.
- [x] The `codebase` argv is asserted unchanged in the same test file, so the
      fix cannot silently alter the `--all` path.
      — `test_gito_codebase_argv_is_unchanged`: `--all`, `--path <repo>`, and
      neither `--what` nor `--vs`.
- [x] The `worktree` argv is asserted to carry **no** `--what`, so the fix
      cannot regress `--scope changes` into reviewing the committed head.
      — `test_gito_worktree_argv_has_no_head`. The implementation branches on
      `scope == "branch_delta"` explicitly rather than on "not codebase", so
      worktree cannot acquire a head by falling through.
- [x] The refusal is asserted in-pack and is provider-scoped: a `branch`/`pr`
      run selecting gito against a clean tree whose `HEAD` is not the requested
      head raises `ReviewInputError` with a message naming both oids, and the
      same run selecting prism only still succeeds. The second half is the
      regression guard for a capability prism was measured to have; without it,
      a later collapse of the check into `resolve_target` passes its own tests
      while silently removing that capability.
      — `test_gito_refuses_a_head_the_working_tree_does_not_hold` (asserts on
      the message naming both oids, not the exception type, because the
      dirty-tree guard raises the same type) and
      `test_prism_still_reviews_a_head_the_working_tree_does_not_hold`. The
      refusal is a declared provider property, `requiresTreeAtHead`, not an
      `adapter == "gito"` test at the call site.
      A third test was added that the criterion did not ask for:
      `test_a_symbolic_head_that_resolves_to_the_tree_is_not_refused`. The gate
      flagged this change as adding a `normalization-evidence` boundary risk —
      the guard compares two oids, so `--head feature` must not be refused for
      not being spelled like the oid it resolves to. Covering it was cheaper
      than dispositioning it.
- [x] External evidence, in two halves. From a working tree that is *not* the
      head, the stage **refuses by name** rather than returning findings — see
      `design.md`, which establishes that gito reads file content from the
      working tree, so a correct review of an unheld head is not available from
      this provider. From a worktree that *is* the head, a replay of
      `sd-github-review` PR #70 returns findings confined to the range. Neither
      half can be asserted from inside the pack.

      This criterion originally read "returns findings confined to the range"
      for the not-the-head case. That was written before the experiment and was
      unsatisfiable as stated.

      **MET 2026-08-25**, both halves, against `platypeeps/sd-github-review`
      PR #70 (`c3ec5f64...2880186`, 23 files) with real gito v4.4.4.

      *Not the head* — tree at `8f5a4099dcd1`, head requested `2880186745ad`.
      Before: 18 findings, **13 citing files outside the 23-file diff**, exit 1,
      receipt recording the correct head. After: exit 2, `outcome: "invalid"`,
      `provider(s) gito read file content from the working tree, which does not
      hold the requested head: planned 2880186745ad…, checked out 8f5a4099dcd1…`.

      *At the head* — detached worktree at `2880186745ad`, clean. **3 findings,
      0 out of range.** gito's own log line changes from
      `Making merge-base diff: INDEX vs c3ec5f64…` to
      `Making merge-base diff: 2880186745ad… vs c3ec5f64…`, so the mechanism is
      visible in the provider's output rather than only in the argv.

      Method, recorded because it is weaker than a release in one respect: the
      fix branch's script was run directly against the consumer rather than
      through an installed release, so this evidences the *behaviour* and not
      the *packaging*. That the installed machine layer delivers it is a
      release-time check, and worth doing — the previous replay found that layer
      eighteen versions behind the plugin cache.

## Notes

Filed 2026-08-25 from the consumer side. Planned 2026-08-25: `design.md` and
`implement.md` are written, and requirement 2 is settled by experiment — passing
`--what` is *not* sufficient, because gito resolves the diff from refs but reads
file content from the working tree. The stage refuses instead, and the refusal is
scoped to providers that declare the defect; `prism` was tested and does not.
See `design.md` for the experiment table.
