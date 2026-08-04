# Trellis-upstream + controller follow-up notes (0.64.4)

Items that are NOT shippable from sd-ai-command-pack's install payload. Recorded
here during planning; formal filing against the Trellis tool happens in
implement.md Phase D #10.

## Trellis-upstream (external `trellis init` scaffolds these; this pack does not ship them)

These live in `.trellis/scripts/{task.py,common/task_store.py,add_session.py}`,
scaffolded by the external `trellis init` (no `templates/.trellis` in this pack;
`install.py` uses `trellis_init_platforms`). Editing this repo's local copies would
patch only this repo, not consumers — false confidence. File upstream instead.

- **#1 require `--description` (root)** — `task_store.py:300-314` currently warns but
  persists an empty description. Upstream ask: `task.py create` with `--description ""`
  or omitted should hard-error (or default from title). Pack-side compensating control
  shipped: fleet checkout-validation guard (AC1.c).
- **#5 `_example` seed rows (root)** — `task_store.py:162-170,352-356` writes a lone
  `_example` scaffold into `implement.jsonl`/`check.jsonl`. Upstream ask: `--no-start`
  / lightweight create leaves manifests empty. Pack-side compensating control shipped:
  review-preflight treats a lone scaffold row as advisory, not `task_context_seed`
  (AC1.b).
- **#4 `add_session.py` real subject (root)** — `add_session.py:222` writes
  `(see git log)` placeholders. Upstream ask: resolve `git log -1 --format=%s <hash>`
  at generation. Pack-side compensating control shipped: the publish helper uses the
  existing `record-session.py` wrapper, which already resolves real subjects (AC2.c).

## Controller follow-up (in-repo, but out of 0.64.4 scope — needs its own design)

- **#12 redo-lane relink — DESCOPED (C-4).** A `resume --relink-pr` that mutates
  `lane["head"]/["prNumber"]` directly breaks the publication-epoch invariant
  (`validate_state` at fleet-controller.py:681/690) and lets the receipt guards
  (1182) validate against mutated expectations — a naked relink could redefine the
  expected PR/head so later forged evidence passes. Not safe to ship as designed.
  - **0.64.4 recovery (retained):** fresh-campaign redo — attest
    checkout-validation..local-checks as `passed`, record pr-publication with the
    existing head + new PR (first publication in the fresh ledger). Proven 4×.
  - **Follow-up design:** a typed recovery record carrying old→new PR+head,
    reason/provenance, requiring no outstanding issued action, resetting the lane to
    `pr-publication`; the lane head changes ONLY when the new publication receipt
    establishes the new epoch. Tests: misuse (relink with an issued action pending),
    persisted-state round-trip, and a guard that pre-relink evidence cannot pass
    post-relink.
