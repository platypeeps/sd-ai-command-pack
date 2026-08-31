---
name: sd-gate-probes
description: Use when a change or plan is about to be offered for review — at a commit boundary, before a pull request is opened, or when asked to run pre-merge quality probes over a diff or an implementation plan. Probes report findings; the sd-review lane holds the review verdict.
---

# SE Gate Probes

Run eleven universal quality probes over a diff or an implementation plan
before it is offered for review. The probes catch scope, duplication,
coherence, and plan-quality defects early, so the review lane spends its
attention on judgment rather than mechanics. Every probe returns PASS,
FAIL, or UNSCORED with evidence; a FAIL either blocks the gate or warns,
per the table below. UNSCORED is for a probe that applies but whose
evidence this run could not obtain — a command that would not run, a plan
section the artifact does not contain. A probe that does not apply to the
artifact at all is not-applicable, not UNSCORED, and neither is a PASS.

This skill inspects and reports. It never commits, pushes, or edits the
change it is probing, and it never issues a review verdict.

## When to use

Use at every pre-review boundary: before committing a coherent batch,
before opening a pull request, or before an implementation plan is
submitted for approval. Probes 1–7 apply to code diffs; probes 8–11 apply
to plans and implementation specs. Run whichever set matches the artifact;
run both when a change ships with its plan.

Do not use as a substitute for review. The sd-review lane owns the review
verdict on a diff or pull request; `trellis-check` owns spec-conformance
checking with self-fixes. This skill feeds both, replaces neither.

## Arguments

None. The artifact to probe is the current working-tree diff, the named
branch or commit range, or the plan text supplied with the invocation;
confirm which one before probing.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Identify the artifact: a diff (working tree, staged, or a commit
   range) or a plan document. Enumerate the changed files or the plan
   steps so every probe cites concrete evidence. Record the request the
   artifact answers in the same breath — the task brief, the issue, the
   user's stated goal — and quote it. The scope probes below judge the
   change against that request, so an unrecorded request makes the sprawl
   and traceability probes UNSCORED rather than PASS.
2. Run the applicable probes, gathering one line of evidence per probe:

   **Quality probes (diffs):**
   1. *Sprawl* — is the change larger than the request demands? Count
      changed files and lines against the stated goal.
   2. *Duplication* — does the change reimplement something the codebase
      already has? Search for existing helpers before accepting new ones.
   3. *God modules* — does the change concentrate unrelated
      responsibilities into one file or module?
   4. *Reviewability* — can a reviewer follow the diff top to bottom?
      Flag mixed refactors, drive-by renames, and unexplained moves.

   **Surgical discipline (diffs):**
   5. *Traceability* — every changed line traces to the request that
      motivated it.
   6. *Unrelated findings* — problems noticed nearby are reported, not
      fixed in this change.

   **Coherence (diffs):**
   7. *Whole-file re-read* — re-read each modified file in full after
      editing. A diff that looks correct in isolation can leave
      duplicated logic, inconsistent naming, orphaned imports, or a
      function that no longer fits the module's flow.

   **Plan probes (plans and specs):**
   8. *Verifiable steps* — each step is independently verifiable, with
      exit criteria that are testable rather than subjective.
   9. *Explicit dependencies* — ordering constraints between steps are
      stated, not implied.
   10. *Rollback points* — the plan names where and how to roll back if a
       step fails.
   11. *Blast radius* — the plan enumerates everything the change can
       affect, not only the files it edits.

3. Score each probe PASS or FAIL and apply the gate policy:

   | # | Probe | On FAIL |
   |---|-------|---------|
   | 1 | Sprawl | Block |
   | 2 | Duplication | Block |
   | 3 | God modules | Warn |
   | 4 | Reviewability | Block |
   | 5 | Traceability | Block |
   | 6 | Unrelated findings fixed in-diff | Warn |
   | 7 | Whole-file coherence | Block |
   | 8 | Verifiable steps | Block |
   | 9 | Explicit dependencies | Warn |
   | 10 | Rollback points | Block |
   | 11 | Blast radius | Block |

   Score every applicable probe before reporting — a gate that stops at
   the first blocking FAIL sends the author back for one fix at a time,
   when the whole list was available in one pass. Then any blocking FAIL
   fails the gate: report the complete scorecard and do not hand the
   artifact onward until the blocking rows are resolved or the user
   overrides. Warn-level FAILs are reported with evidence but do not stop
   the gate.

4. Route onward — never repeating work already done for this artifact:

   | Condition | Route |
   |---|---|
   | Rust diff (`.rs`, `Cargo.toml`, clippy config) | `sd-rust-review` |
   | Rust module or crate layout change | `sd-rust-modules` |
   | ADR or decision-record change | `sd-adr-review` |
   | Checked-in documentation change | `sd-docs-bustest` |
   | User-facing prose to check in or send | `sd-prose-lint`, `sd-humanizer` |
   | Spec and convention conformance with self-fix | `trellis-check` |
   | Review verdict on the diff or pull request | the sd-review lane |
   | Trellis task state and boundaries | `task.py` (`task.py current`) |

   If a routed sibling is unavailable on this platform, say so instead
   of silently skipping it.

## Safety rules

- Probes report findings; the sd-review lane holds the review verdict.
  Never present a gate PASS as a completed review, never claim "review
  this diff" authority, and never mark review requirements satisfied on
  the strength of this skill alone.
- This skill is read-only toward the artifact: no edits, no commits, no
  pushes, and no fixing of unrelated findings (probe 6 exists to prevent
  exactly that).
- Never invent evidence. A probe without a concrete citation — file,
  line, step number, or command output — is UNSCORED, and an UNSCORED
  probe whose FAIL would have blocked the gate blocks it too. Missing
  evidence fails loud; it never resolves to a quiet PASS.
- Route only to surfaces this pack ships: `trellis-check`, the sd-review
  lane, `task.py` surfaces, and sibling `se-*` skills by their final
  names. Do not route to anything else.
- A user override of a blocking FAIL is recorded in the report as an
  override, never rescored as a PASS.

## Final report

- **Gate probe results** — the table of probe / status / evidence for
  every applicable probe, each PASS, FAIL, or UNSCORED, with probes that
  do not apply to this artifact marked not-applicable and why;
- **Gate verdict** — PASS, or FAIL with the blocking findings listed
  first, warn-level findings after, and any blocking-scope UNSCORED probe
  among the blockers;
- **Overrides** — any user-accepted blocking FAIL, stated as an override;
- **Next step** — the routing rows that apply, each marked `not run`, and
  a reminder that the review verdict belongs to the sd-review lane.
