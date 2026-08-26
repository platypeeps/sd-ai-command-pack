# Design — gito adapter drops the head ref

## What the experiment settled

The PRD left requirement 2 open: "either the head reaches the provider, or the
stage refuses." Passing `--what` looked sufficient. It is not.

Four runs against synthetic two-commit repositories with gito 4.4.4, varying
only the checkout and the argv:

| working tree | argv | outcome |
| --- | --- | --- |
| at base (≠ head) | `--vs <base>` (today) | `Making merge-base diff: INDEX vs <base>`; reviews checkout-against-base. Silent wrong range. |
| at base, head **adds** a file | `--what <head> --vs <base>` | correct diff line, then `KeyError: "Blob or Tree named 'head_only.txt' not found"` — crash |
| at base, head **modifies** a file | `--what <head> --vs <base>` | correct diff line, report produced, **content read from the base** |
| at head | `--what <head> --vs <base>` | correct diff line, correct content, review proceeds |

The third row is the important one. gito resolved the right diff and then read
`mod.py` from the working tree, which held the base's content. The review it
produced contains a fabricated finding:

> "Inconsistency between diff and final file content. The diff shows the
> function was changed to return 2, but the full file content after applying
> changes still shows `return 1`. This indicates the diff and the final file are
> out of sync, suggesting a tooling or versioning error…"

That is the tool describing its own misconfiguration as a defect in the
repository under review, at `severity: 1, confidence: 1`, attributed to
`mod.py`.

**Mechanism: gito 4.4.4 resolves the diff from refs but reads file content from
the working tree.** Passing `--what` therefore converts a silent wrong-range
review into either a crash (added paths) or a differently-wrong review that
invents findings (modified paths). It is necessary and not sufficient.

## Consequence for the fix

The stage cannot delegate head-binding to the provider. It must guarantee that
the working tree *is* the planned head, or refuse to run. Requirement 2 resolves
toward refusal.

## Scope split: three cases, not two

The PRD says "only the delta branch is wrong". That is one code branch but two
canonical scopes. `_expand_argv` (the PRD's original `_provider_argv` names nothing) tests
`scope == "codebase"` and sends everything else down one path, and
`CANONICAL_SCOPES` is `{"worktree", "branch_delta", "codebase"}`:

- **`worktree`** (from `--scope changes`): `resolve_target` sets
  `base_oid = head_oid`, and the review subject *is* the uncommitted tree.
  `INDEX vs HEAD` is exactly right. Passing `--what` here would be a regression
  — it would review the committed head and discard the changes under review.
- **`branch_delta`** (from `--scope branch` / `--scope pr`): the defect. Needs
  the head, and needs the tree to hold it.
- **`codebase`**: `--all --path`. Unchanged.

So the gito branch splits three ways. A fix that keys off "not codebase" repeats
the original error in the opposite direction.

## Where the invariant belongs

**Not** in `resolve_target`. An earlier draft of this design put it there,
arguing the invariant is provider-independent and that exempting `prism` would
be an assumption rather than a finding. The adversarial review tested `prism`
instead of assuming, and the argument does not survive.

Same synthetic method, tree at the base, head introducing defects the tree does
not contain (`os.system` on a caller-supplied string, `eval` on the same,
an unconditional `rm -rf`):

```
$ prism review range <base>..<head> --format json      # tree checked out at <base>
findings: 4
 - high Arbitrary OS command injection via os.system
 - high Destructive rm -rf executed unconditionally on every call
 - high Arbitrary code execution via eval on untrusted input
 - medium Return value semantics changed from length to eval result
```

Prism reported the head's defects while the working tree held only
`return len(payload)`. **Prism reads content from refs.** It does not share
gito's defect, and it can correctly review a range that is not checked out.

A refusal in `resolve_target` would therefore remove a capability prism
demonstrably has, to work around a bug prism does not have. The constraint is a
property of the *provider*, not of the plan.

Enforce it as a declared provider property instead: the built-in gito provider
declares that it requires the working tree to hold the planned head, and the
stage refuses before dispatching that provider for `branch_delta` when `HEAD`
is not the target head. Declaring it — rather than hard-coding `adapter ==
"gito"` at the check site — matters because a consumer-configured `argv`
provider can wrap gito (`prism-chunked` is exactly such a provider), and a
hard-coded check would not see it.

The general capability-declaration system is larger than this defect; this task
adds the one property gito needs, shaped so an `argv` provider can opt in, and
parks the general system.

## Chosen shape

1. The built-in gito provider declares that it requires the working tree to hold
   the planned head. Before dispatching a provider carrying that declaration for
   `branch_delta`, the stage compares the target head to the tree's own `HEAD`
   and, on mismatch, refuses with a `ReviewInputError` naming both oids and the
   remedy (check out the head, or run from a worktree at it). Providers without
   the declaration — `prism`, and any `argv` provider that does not opt in — are
   unaffected and keep reviewing ranges that are not checked out.
2. Gito branch of `_expand_argv`: for `branch_delta`, emit
   `["gito", "review", "--what", head, "--vs", base, "--out", output]`.
   For `worktree`, keep today's `--vs base` with no `--what`. For `codebase`,
   unchanged.
3. `--what` is redundant once (1) holds, and is passed anyway: it makes the argv
   self-describing in `invocation.json`, and it means a future relaxation of (1)
   fails loudly rather than silently.

## Rejected alternatives

- **Pass `--what` only.** Rejected: the experiment shows this yields crashes and
  fabricated findings rather than correct reviews.
- **Have the stage create a detached worktree at the head.** Preserves the
  ability to review a ref that is not checked out — the capability (1) removes.
  Rejected *for this task*: worktree lifecycle, cleanup on interrupt, artifact
  roots that must stay inside the repository, and concurrent-run collision are
  each larger than this defect. Parked, with the operator doing manually what the
  stage will not do implicitly — which is what the criterion-6 replay already
  did by hand.
- **Warn instead of refuse.** Rejected: this defect's whole character is that it
  is severity-free and silent. A warning on a stage that already prints info
  lines reproduces it.
- **Refuse in `resolve_target`, for every provider.** Rejected on evidence: see
  **Where the invariant belongs**. It would break prism's working ability to
  review a range that is not checked out.

## Compatibility and rollout

Behaviour change: `--scope branch|pr` invoked from a tree that is not the head
now fails fast **when gito is among the selected providers**, where it previously
produced a confident wrong answer. Prism-only and non-opted-in `argv` runs are
unchanged. This matters for `--local auto`, which selected gito exclusively
throughout the 0.71.51 rollout: in practice most runs will carry the constraint.

No consumer config changes. No receipt schema change; the refusal happens before
a receipt is written.

Rollback is the inverse commit; nothing persists state.

## Validation

`tests/test_review_stage.py:597` currently asserts `"gito review --vs"` in the
invocation log. That assertion pins the defect and must change — it is the
anchor for "the test fails against today's code".
