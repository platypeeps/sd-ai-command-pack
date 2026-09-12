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
External review uses the operator's standing machine policy, with local restrictions and existing spending limits.
Read `sd config get sd.external_reviews` and `sd config get sd.merge_authorization`; these settings are never granted by installation.
`sd.merge_authorization` is read by the assistant, not by `sd-ship`; the tool merges whatever the gates let through, and the setting decides whether to ask it to.
With `controlled` merge authorization, finish active in-scope PR work through existing gates unless the user explicitly says wait.
Shared contributors do not revoke user permission, but existing ownership gates still apply; do not bypass a refusal.

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

## Calling Convention

The pack's executables live in `bin/` and are invoked by path, relative to the
checkout: `bin/sd`, `bin/sd-status`, `bin/sd-review`. That is how the
installed hooks invoke them, and it is the only convention the repository
supports.

The installer renders surfaces -- skills, agents, companions, hooks -- and links
no executable anywhere. So `installed.json` is a receipt for those surfaces, not
evidence that any command resolves in a shell, and an absent binary in it is not
a partial install. Where `sd` or `sd-research-kit` do resolve on a machine, a
hand-made symlink under `~/bin/common` points back into a checkout; the install
did not put it there and does not know about it.

To see what holds on the machine in front of you, run the installer's status
command rather than reading a list: its `commands:` line enumerates `bin/` and
`PATH` at runtime, and says whether a command resolves elsewhere.

## What a Document Owns

A document owns the scope it describes, never the argv that reached it. A page
about this pack's rules describes this pack's rules whichever command opened
it, and a path written for the reader's own checkout stays unqualified. One
ruling settles all three of the questions that kept arriving separately, so
there is nothing further to decide case by case.

It applies to **live text only.** A preserved review body, an archived work
item, and `CHANGELOG.md` are records of what was said at a time, not claims
about what holds now. Rewriting one to match today's scope destroys the record
it exists to keep.

Two consequences, both enforced rather than remembered:

- **A provenance citation needs no qualifying.** Naming where a fact came from
  is not an instruction to go and open it, so no prose beside it has to say
  whose checkout holds the file.
- **The qualifying guard stays scoped to `.claude/rules/`.** That is the one
  surface this pack authors, tells the reader to go and read for authoritative
  content, and cannot install into the reader's checkout. Per-repository
  configuration that the reader's checkout is supposed to carry -- the files
  `bin/sd_setup_github.py` writes under `.github/` -- is correct unqualified,
  and naming the pack beside one would be the worse bug. The reasoning, and
  both ends of the scan enumerated from the filesystem, are in
  `tests/test_doc_citations.py`.

## When the Git Wrapper Is Refused

In a worktree-isolated session the hook rewrites `git ...` into a wrapped form,
and the isolation guard refuses it: the guard cannot verify that a wrapped
command stays inside the worktree. That guard lives in the Claude Code binary,
not in this pack, so nothing here can teach it the wrapped form.

Call `/usr/bin/git` instead, which the guard reads directly, and say in the
report that you fell back to it. Do not edit the wrapper's configuration to get
past the refusal. Its exclusion list is machine-global while the refusal is
per-session, so switching it off for one worktree switches it off for every
repository on the machine.

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
