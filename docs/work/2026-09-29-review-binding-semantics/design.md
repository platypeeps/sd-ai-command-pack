# Design — review binding semantics

## What a receipt must stay true to

A review receipt is the stored `sd-review` report for one head. Two kinds of
code touch it, and they age differently.

- **Producer code** ran once, inside the `sd-review` process, when the
  receipt was made. It chose the providers, built the prompt, ran the
  deterministic check, and parsed and classified the findings. A later
  change to it means a new review could differ from the stored one. The
  receipt cannot be re-derived, so the binding must catch the change.
- **Gate code** runs again on every `prepare` and `merge`. `review_inputs`,
  `complete_report`, `validate_findings`, `validate_provider_selection`,
  `history.validate_coverage` and `sd_ship_dispositions.accepted` all read
  the stored report with the code on disk now. A gate change already applies
  to old receipts. Binding it adds a review pass and no evidence.

The deterministic check is a third case. `sd-review` runs `sd-check` before
it dispatches (`run_check` in `bin/sd-review`), and the prompt does not carry
the check output (`build_prompt` takes the subject, the stance and the
conventions only). The merge gate runs the check again at the landing head:
`sd_local_gate.local_gate` for `repo.ci=local`, the required GitHub checks
otherwise. `sd-docs-lint` runs from `bin/sd-ship` (the pre-publish lint and
`--body-only`), so it is gate code, not review code.

## Classes

The class map lives in `bin/sd_ship_bindings.py` as four tuples. Class is
read from the code that validates, never from the stored receipt.

| Class | Members | In digest | Compared by |
|---|---|---|---|
| `verdict` | `sd-review`, `sd_lib.py`, `sd_registry.py`, `sd_route.py`, `sd_codex.py`, `sd_review_material.py`, `sd_review_readiness.py`, `sd_jev.py` (new), `sd_opencode.py` (new), `sd_review_request.py` (new, see below) | yes | normalized hash |
| `policy` | `CLAUDE.local.md` block, `.github/sd-review.json`, `external_reviews` setting | yes | raw hash, as today |
| `gate` | `sd-ship`, every `sd_ship_*.py`, `sd_protection.py`, `sd_local_gate.py`, `sd-docs-lint` | no | recorded raw, named only |
| `check` | `sd-check`, `sd_check_receipts.py`, `sd_gate_slots.py` (new) | no | recorded raw, named only |

Evidence for the two new `verdict` members: `sd-review` calls
`sd_jev.jev_tier` to choose the review tier, and `sd_opencode.opencode_answer`
with `parse=parse_findings` to turn an opencode answer into findings.
`sd_setup_github.py` and `sd_setup_guard.py` are also imported by `sd-review`,
only for the `setup-github` subcommand; they go on a named exemption list
with that reason.

`sd_ship_review.py` is gate code with one producer function, `review_argv`.
It fixes `--scope branch` and `--challenge`, the stance the reviewer takes.
The plan moves that function to a new `bin/sd_review_request.py` in the
`verdict` class, so `sd_ship_review.py` can be `gate`. The pass base and
the prior report are recorded per pass and checked live by
`validate_coverage`, so they stay gate concerns.

## Normalized hash

For a `verdict` file: `ast.parse` the source, drop the docstring of the
module and of each class and function, and hash
`ast.dump(tree, include_attributes=False)` with a normalizer tag
`ast-docstring-1/py<major>.<minor>`. Comments and layout are gone after
parsing. Every other string literal stays: prompt text, log text and refusal
text are all literals in `sd-review`, and the normalizer cannot tell a prompt
from a log line. Treating log strings as semantic costs little: they rarely
change alone.

Rules:

- A file that does not parse is hashed raw, tagged `raw`. Never skip it.
- The Python version is in the tag. A new interpreter moves every receipt
  once, and the refusal says "normalizer changed" instead of naming files.
- A test fails if a `verdict` file reads `__doc__`, `inspect.getdoc` or
  `inspect.getsource`. Measured 2026-09-29: none does.

## Digest and manifest

`review_binding(root)` becomes `digest({"schema": 2, "normalizer": tag,
"verdict": {name: normalized}, "policy": {...}})`. The value stays a string
in `state["binding"]`, so `sd_ship_dispositions.context` and every exact
comparison keep working unchanged.

`binding_manifest(root)` returns the same entries plus `gate` and `check`
raw hashes. `execute_review` stores it as `state["binding_manifest"]` in the
same `save` that stores `binding`, and `DISPATCH_FIELDS` gains it so a
released gate failure restores it.

`binding_change(state, root)` replaces the two inline comparisons in
`SharedReview` (`review_inputs` and `binding_moved`). It returns `None` when
the digests match, else a list of `(entry, class)` that differ. A missing
stored manifest returns the single entry `("receipt predates the per-file
manifest", "legacy")`. Gate and check entries that differ ride along in the
list, marked, so the operator sees them; they never cause the refusal alone,
because the refusal is decided by the digest.

Storing a content-addressed copy of each bound file was considered and
dropped. The raw hash is a git blob hash away from the file:
`git log --all --find-object=<blob>` in the pack finds the version. A copy
per receipt costs storage for no decision.

## Refusal

The text keeps its prefix, so existing matchers still match:

    review tools or repository policy changed after review: sd-review (verdict),
    .github/sd-review.json (policy); also changed, not binding: sd-ship (gate)

At most five entries per class, then "and N more". The refusal gains
`code="review_binding_moved"` and `next_action="Run sd-ship prepare again;
it re-reviews this head in full (sd:1390)."`. The `review_binding_change`
record on the re-review pass gains `changed` with the same list.

## Adjudicator binding

`adjudicator_binding` today is `tool_files()` (the raw 25) plus the `sd_db`
ship library, the five `ADJUDICATOR_POLICY_FILES` and the skill references.
It becomes the `verdict` normalized hashes plus those raw entries.
Acceptance of a disposition is an explicit operator decision against written
rules, so the rules (skills, references, library) stay raw. The disposition
validator itself is gate code and runs live.

## Migration

Every stored receipt has a schema-1 digest and no manifest. After the change
lands, the schema-2 digest differs, so each open receipt is moved exactly
once and re-reviews through the sd:1390 path. Accepted dispositions bind
the old `adjudicator_binding` and need one re-acceptance. This follows the
archived rule: never backfill a binding from current files. It is the same
cost as one ordinary bound landing today, paid once.

## Options considered

| Option | Verdict | Evidence |
|---|---|---|
| A. Narrow the file set only | Part of the design | Alone it keeps 68 of 162 landings (gate and check only). |
| B. Normalized hash only | Part of the design | Alone it keeps 11 of 162. |
| C. Per-file manifest, name the change | Part of the design | Needed for sd:1246 and for honest legacy handling. |
| A+B+C, as above | Recommended | Keeps 73 of 162 (45%); 52 of 109 since 2026-09-15. |
| D. Pack identity claim | Rejected | A commit moves on every pack landing, a strict superset of today's 162. The installed pack runs from a checkout that is often dirty or mid-branch and cannot name a commit. Tags (`v1.0.0`) are not what runs. |
| E. Re-derive plan and prompt at merge | Deferred | Would bind what the reviewer saw rather than code. Needs an `sd-review --explain` run and a prompt digest per provider at every `prepare`; larger build. |
| F. Symbol-level `sd_lib.py` binding | Optional slice 4 | 41 of the 89 remaining moves touch `sd_lib.py` as their only `verdict` file. A static reachability closure from the `verdict` modules reaches 130 of 212 top-level names and keeps 14 more (87 of 162, 54%). It would have kept pack #1234. |
| Hash the shipped repository's `bin/` | Rejected | Fatal outside the pack; recorded in sd:1397. |

Of the named incidents: #1234 (`sd-ship`, `sd_lib.py`) still moves under the
recommended design, because it adds a function to `sd_lib.py`; option F keeps
it. #1233 (`sd-review`, `sd_registry.py`) adds a provider kind and moves
under every option but E. #1126 (`sd-docs-lint`, `sd_jev.py`) survives: its
`sd_jev.py` change is docstring/comment-only under the normalizer (measured
2026-09-29), and `sd-docs-lint` is `gate`.

## Risks

- A module moved to `gate` that in fact shapes a verdict loses protection.
  The import walk and the class table are the control; a reviewer of this
  plan should challenge each `gate` row.
- A gate tightening that needs a new report field now refuses an old
  receipt as incomplete rather than re-reviewing it. That is the right
  answer and the current message says so.
- The normalizer depends on `ast.dump` stability within one Python minor
  version. The tag makes a change visible.
