# Local disposition reasons cannot name a key=value argument

## Goal

`--local-disposition '<id>=accepted@<reason>'` refuses any reason containing
`=`. This pack's own argument vocabulary is `key=value`, so the natural way to
write an acceptance reason names arguments — `input=`, `exclude=`,
`sensitivity=`, `min_severity=`. Those are exactly the reasons a reviewer
writes, because arguments are what findings are usually about.

Reported as issue #591 from an `sd-work-backlog` run in
`platypeeps/se-ai-command-pack` (PR #278), pack 0.71.62.

## Evidence

At report time `templates/scripts/sd-ai-command-pack-review.py` and
`templates/scripts/sd-ai-command-pack-review-local.py` both parsed the
option with `value.rpartition("=")`, which splits on the **last** `=`. For
`L-3=accepted@the corpus is input= minus exclude=` that puts the whole verb and
reason into the identifier and leaves the remainder empty, so the value fails
the vocabulary check. Each file then re-inspected the token on the failure path
solely to report the trap by name:

```
an accepted reason cannot contain '='
```

Two reasons had to be rewritten mid-run to get past it:

- ``the corpus is `input=` minus `exclude=` `` → "the corpus is the input
  argument minus the exclude argument"
- the same for a `sensitivity=` carve-out

That rewrite is strictly worse as an audit record. `accepted` is the one
disposition ground that concedes the finding is real and leaves the stated
basis as the only thing a later reader can check, so degrading the reason
degrades the exact artifact the ground exists to produce.

The `rpartition` was chosen so that an identifier containing `=` would keep
parsing; both files say so in a comment. No identifier can contain `=`:
`SAFE_ID_RE` in the controller is `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` and
`ID_RE` in the stage is `[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*`. Neither admits
`=`, so the capability the split was protecting cannot be reached by any
identifier the pack mints, while the cost it imposes falls on every reason and
path that names an argument.

## Requirements

- Split the option on the **first** `=`, so the identifier ends at that
  separator and everything after it — verb, `@`, and payload — is the
  disposition value.
- Take the `@` payload verbatim. A reason or a citation path may contain `=`,
  and no new escape syntax is introduced to permit it.
- Apply the change in both parsers. The controller's copy gates: a value it
  rejects never reaches the stage that owns the authoritative grammar, so
  fixing only the stage leaves the option unreachable through the documented
  entry point.
- Remove the failure-path `=` diagnostics in both files, and the comments
  asserting the identifier-with-`=` rationale. They describe a trap that no
  longer exists.
- Preserve every other rejection: unknown verb, empty identifier, an
  identifier over 240 bytes, control characters, a duplicate identifier, a
  missing payload for `miscited` and `accepted`, and an `@` payload on a verb
  that takes none.

## Acceptance Criteria

- [x] `--local-disposition 'L-3=accepted@the corpus is input= minus exclude='`
      is accepted, and the recorded reason is byte-identical to the text after
      the first `@`.
- [x] `--local-disposition 'abc=miscited@a=b.py:3'` is accepted and cites path
      `a=b.py` at line 3.
- [x] Neither script contains the string `cannot contain '='`.
- [x] The existing rows that pin the `=` refusal are gone from
      `tests/test_review_controller.py` and `tests/test_review_stage.py`, and
      each file gains an acceptance test in their place that checks the parsed
      payload rather than only the exit status. Both files, because the
      controller gates: an acceptance pinned only in the stage leaves the
      option unreachable through the documented entry point.
- [x] Every other malformed-value rejection listed above keeps its existing
      message and exit status, pinned by test.
