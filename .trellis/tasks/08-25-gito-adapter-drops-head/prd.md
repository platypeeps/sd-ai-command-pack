# Local stage gito adapter drops the head ref

The local stage resolves a review target as a `(base, head)` pair and records
both in the receipt, but the gito adapter only ever transmits the base. gito
supplies its own head from the working tree, so the range actually reviewed is
`base..<whatever is checked out>` rather than `base..head`.

## Evidence

`templates/scripts/sd-ai-command-pack-review-local.py`, in `_provider_argv`,
builds the delta invocation as:

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
diff at all**, several in paths created months after that head
(`docs/RELEASE_CHECKLIST.md`, `package.json`,
`.trellis/tasks/08-09-review-gate-advisory-convergence/design.md`). Only one
finding fell inside the range.

Rerunning the identical command from a detached worktree whose tree *was* the
head returned 5 findings, all in range — matching the shape the consumer's PRD
records for its earlier gito replay of the same range.

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
3. The codebase-scope branch keeps its current behaviour; only the delta branch
   is wrong.

## Acceptance criteria

- [ ] `_provider_argv` passes the resolved head to gito for delta scopes,
      asserted by a test on the constructed argv that fails against today's code.
- [ ] The same test pins the base argument, so a fix that swaps the two —
      reviewing `head..base` — fails rather than passing on argv length alone.
- [ ] The codebase-scope argv is asserted unchanged in the same test file, so the
      fix cannot silently alter the `--all` path.
- [ ] External evidence: a replay of `sd-github-review` PR #70 from a working
      tree that is *not* the head returns findings confined to the range. This is
      what the defect broke, and it cannot be asserted from inside the pack.

## Notes

Filed 2026-08-25 from the consumer side. Not planned — `design.md` and
`implement.md` are unwritten, and requirement 2 is a real open question: passing
`--what` may be sufficient, or the stage may need to refuse when the working tree
cannot be bound to the planned head. Settle that before `task.py start`.
