---
title: Correct two stale citations left by the Codex-lane removal
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-11
---
# Correct two stale citations left by the Codex-lane removal

## Goal

Two files shipped by `08-11-thin-undeclared-codex-marker` (PR #424, pack
0.68.0) cite something that is not true of the code they describe. Neither
breaks a test, which is exactly why they will survive until someone reads them
and believes them. Correct both.

Both were raised as suppressed comments on Copilot's fourth review round of
PR #424, against head `fd752ae6`, and both were verified against the
repository before this task was written.

## Requirements

### R1 — the test comment claims the contract names a lane it does not name

`tests/test_claude_planning_review.py:125-131`, inside
`test_host_contract_carries_no_codex_invocation`, reads:

```python
        # ... Assert on the invocation, not
        # on the word: the contract still *names* the lane, and must, or the
        # capability would be undiscoverable.
```

The shipped contract names nothing of the sort. Measured:

```
$ grep -ci codex templates/.claude/sd-ai-command-pack/planning-adversarial-review.md
0
```

The comment is a survivor of the rejected option-5 draft, in which the shipped
contract did name the Codex lane and link to it conditionally. Option 3 ships a
contract that speaks only of "an additional independent lane" in the abstract,
and the test three lines below asserts `assertNotIn("planning-adversarial-review-codex", reference)` —
the opposite of what the comment says the file must do.

Rewrite the comment to state what the test actually protects: the shipped
contract carries no Codex CLI invocation and no pointer to a lane a consumer
cannot obtain. Do not weaken the assertions; they are correct as written.

### R2 — the spec quotes an assertion that is not in the code

`.trellis/spec/backend/manifest-and-filesystem.md:1125` quotes:

> `assertIn("codex", install.PLATFORMS)`

The line it cites is `tests/test_generated_parity.py:1460`:

```python
        self.assertIn("codex", install.PLATFORMS)
```

The spec drops the `self.` receiver. The paragraph's job is to let a reader
jump from the prose to the exact line, and a grep for the quoted string finds
nothing. Quote it exactly.

## Acceptance criteria

- [ ] The comment in `test_host_contract_carries_no_codex_invocation` makes no
      claim about the shipped contract naming the lane, and every claim it does
      make is true of `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`
      as measured, not as remembered.
- [ ] `grep -c 'self.assertIn("codex", install.PLATFORMS)' .trellis/spec/backend/manifest-and-filesystem.md`
      returns 1, and the string as quoted in the spec appears verbatim in
      `tests/test_generated_parity.py`.
- [ ] `.venv/bin/python -m unittest tests.test_claude_planning_review` passes
      with the same 6 tests and no assertion removed or relaxed.
- [ ] `make check` exits 0.

## Non-goals

- No change to the shipped contract, the appendix, the manifest, or the pack
  version. This task edits a test comment and a spec sentence; if a payload
  file changes, the scope was wrong.
- No re-litigation of the option-3 decision. The capability loss was accepted
  twice and is recorded in `08-11-thin-undeclared-codex-marker/design.md` D6.

## Notes

Cheap to batch with any other doc-accuracy work in the same area. Nothing
depends on it, and nothing it touches is executable.
