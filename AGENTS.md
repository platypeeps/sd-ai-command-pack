# sd-ai-command-pack

Instructions for AI assistants working in this repository.

## Maintainer Rules

- Do not create pull requests in the upstream `Trellis` repository without
  explicit approval from the user for that specific upstream PR. If
  `sd-ai-command-pack` work uncovers a `Trellis`-owned change, document the
  finding and provide a paste-ready handoff instead of opening a `Trellis` PR.
- At the planning convergence boundary, follow
  [.claude/rules/sd-planning-adversarial-review.md](.claude/rules/sd-planning-adversarial-review.md).
  That file is the one statement of the rule and holds the review table every
  review point reads its cap from; this bullet states nothing of its own, so
  there is no second copy to drift.
- `skills/**` holds the one copy of the payload. Nothing renders into this
  repository, so there are no copies to keep synchronized: change the skill and
  you have changed the
  only copy.

## Companion Repository Scope

Work started here may also change these companion repositories:

- `/Users/sven/repos/platypeeps/sd-writing-pack`
- `/Users/sven/repos/system`

Treat related implementation, tests, documentation, CI, and coordinated delivery in these repositories as part of this project's scope.
Do not request confirmation solely because an in-scope operation targets either companion repository.
Read each repository's instructions and preserve its existing work before making changes.
This scope exception does not authorize unrelated work or remove specific approval requirements for destructive actions or upstream Trellis PRs.
External reviewer consent remains specific to the approved recipients and task.

## Contributor Entry Points

- Read [CONTRIBUTING.md](CONTRIBUTING.md), then run `make check` before
  publishing a change.
- Read [docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md](docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md)
  before changing the installer or the command set. The `docs/spec/**` pages on
  adapters, manifests, and provenance describe the pre-3e model and are stale
  until later steps reach them.
  - Amended 2026-09-01: no later step reached them. Steps 4 and 7 closed
    without the triage, so each stale page now carries a dated notice at the
    top instead of waiting for one. Read the notice before the page; where it
    says "partly stale" it names which sections still hold. The pages that
    describe only deleted machinery are still on disk pending a deletion
    decision, listed with evidence under step 7 in
    [docs/work/archive/2026-09/2026-08-29-artifacts-as-product/implement.md](docs/work/archive/2026-09/2026-08-29-artifacts-as-product/implement.md).
- Planning artifacts live in [docs/work](docs/work/README.md): one directory per
  item, `prd.md` plus `design.md`/`implement.md` when warranted. That directory
  is the whole tracked footprint of the workflow.

<!-- SD-AI-COMMAND-PACK:ROUTING:START -->
## Canonical Entry Points

The SD AI Command Pack wraps several Trellis workflows. Where a wrapper
exists, it is the canonical entry point: it carries the pack's own gates,
review loop, and completion bookkeeping, and the underlying Trellis command
does not. Reaching past a wrapper to the command it wraps skips those.

Route by intent:

- **Publishing a branch, working its review, and merging it** — use the pack's
  ship workflow rather than invoking the create-PR, review, and merge steps
  separately. It sequences them and owns the stop-points between them.
- **Finishing a task** — use the pack's finish-work workflow. It produces the
  bookkeeping receipt the merge gate independently revalidates.
- **Merging** — go through the pack's housekeeping gate. It is the only merge
  authority; nothing else in the chain merges.
- **Reviewing changes locally before publishing** — use the pack's review
  workflow, which runs the deterministic checks the remote review assumes.
- **Anything with no pack wrapper** — use the Trellis command directly. The
  pack adds surfaces; it does not replace Trellis.

To see which wrappers this repository actually has, list the installed skills
rather than relying on a list written down somewhere: they are the pack's
`sd-*` skills, and the pack's own help surface enumerates them at runtime.

Nothing verifies or rewrites this block any more. The machine-scope installer
never edits a tracked repository file, `AGENTS.md` included, so what follows is
hand-maintained like the rest of the document. It deliberately names no
individual command: the block routes by intent, so there is nothing in it that a
change to the command set could make false.
<!-- SD-AI-COMMAND-PACK:ROUTING:END -->
