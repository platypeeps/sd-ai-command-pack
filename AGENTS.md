# sd-ai-command-pack

Instructions for AI assistants working in this repository.

## Maintainer Rules

- Follow [.claude/rules/sd-operator-defaults.md](.claude/rules/sd-operator-defaults.md) for reviewer selection, STE-Concise, and diagram tooling.
  These defaults apply to both Claude and Codex.
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
- Read [docs/current-architecture.md](docs/current-architecture.md) before changing the installer or command set.
- Read each `docs/spec/**` notice before using that page.
  Some pages describe the retired pre-3e model.
- Planning artifacts live in [docs/work](docs/work/README.md): one directory per
  item, `prd.md` plus `design.md`/`implement.md` when warranted. That directory
  is the whole tracked footprint of the workflow.

## Calling Convention

The pack's executables live in `bin/`. `python3 bin/sd_install.py --user` links each
of them into `~/.local/bin` (`--bin-dir DIR` for another directory) and records
every link in `installed.json`, so once `--user` has run on a machine a bare
`sd`, `sd-status` or `sd-review` resolves from any directory, provided that
directory is on `PATH`; the installer never edits the shell.

Invoking by path, relative to the checkout -- `bin/sd`, `bin/sd-status`,
`bin/sd-review` -- still works and is what the installed hooks and the lane
brief use: a hook names the checkout it was installed from, and a lane reads
the store from the checkout it was given, where a bare name resolves against
whatever `PATH` holds.

The receipt is evidence of the links, not of what resolves: a link in a
directory that is not on `PATH` resolves nowhere. To see what holds on the
machine in front of you, run the installer's status command rather than
reading a list: its `commands:` line enumerates `bin/` and `PATH` at runtime,
counts the commands that resolve from this checkout, names the missing ones,
and says whether a command resolves elsewhere.

Codex exposes these procedures as skills: invoke `$sd-review`, `$sd-ship`, or `$sd-plan`.
Do not expect `/sd-*` entries in its slash-command menu.
Shell commands remain separate; not every skill has an executable.

## What a Document Owns

A document owns the scope it describes, never the argv that reached it. A page
about this pack's rules describes this pack's rules whichever command opened
it, and a path written for the reader's own checkout stays unqualified. One
ruling settles all three of the questions that kept arriving separately, so
there is nothing further to decide case by case.

It applies to **live text only.** Preserved reviews, archived work items, and `CHANGELOG.md` record earlier statements.
Do not rewrite their prose to match current behavior.
Archive moves can add lifecycle metadata without changing the recorded discussion.

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

## Where a Finished Document Goes

`skills/_shared/references/publication-contract.md` is the policy, and it binds
this pack and everything installed from it. Read it before deciding where a
document goes; the short form is here so that nobody has to guess whether one
exists.

**Publication is the default, not a request.** A finished document is written
into the Obsidian vault as Markdown, under `Briefs/<repo>/`, and published to
the local dashboard's **Documents** tab as HTML from `docs/dashboard/`. A
document nobody can find was not delivered, and a skill that ends by naming a
path in a build directory has not finished. Working state -- ledgers, receipts,
handoff packets, monitor state -- is not a finished document and does not
publish.

**The document lives in Obsidian; the rest are duplicates.** Each copy is in the
format its destination reads natively: Markdown in the vault, HTML on the
dashboard, Notion blocks in Notion, a native Google Doc in Drive. A copy in the
wrong format is a copy nobody can use where it landed.

**An outward destination is opt-in, per document.** Notion and Google Drive are
mirrors, not defaults. The user designates a document; it is recorded in that
document's `notion=` or `drive=` key in `research.conf.py`. Nothing infers a
target, and both keys on one entry are two mirrors rather than a choice. A
render enqueues each sync under `~/.claude/pending-mirror-syncs/` and an agent
session drains it, because rendering runs in a git hook and in CI, and neither
can reach an MCP server.

**A Notion mirror is private unless it asks for the team.** `notion=dict()` goes
to the folder `$SD_NOTION_PRIVATE_FOLDER` names; `notion=dict(team=True)` goes
to the one `$SD_NOTION_TEAM_FOLDER` names. Private is the default because a
brief the team cannot see is repaired by draining again, and a private brief in
a shared space has already been read. Both hold a Notion page id, so renaming
either folder moves no document, and an unset one refuses the mirror rather than
guessing a page. The document lands in the repo's own page under that folder,
the shape the vault uses.

**A published page carries its own resources.** The Documents tab serves under
`default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:`.
A `<link>`, a `<script>` or a remote image does not load, and the page renders
degraded rather than failing visibly -- which is why the renderer embeds its
fonts (`bin/sd_research_fonts.py`) instead of linking them. A skill that emits
its own HTML meets the same rule by itself.

The contract is a shared reference, so it reaches an installed skill only if
that skill's `SKILL.md` cites `references/publication-contract.md`. A new
document-producing skill cites it; the installer warns about a citation it
cannot resolve, not about one nobody wrote.

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

The SD AI Command Pack wraps several git and GitHub workflows. Where a wrapper
exists, it is the canonical entry point: it carries the pack's own gates,
review loop, and completion bookkeeping, and the underlying command does not.
Reaching past a wrapper to the command it wraps skips those.

Route by intent:

- **Publishing a branch, working its review, and merging it** — use the pack's
  ship workflow rather than invoking the create-PR, review, and merge steps
  separately. It sequences them and owns the stop-points between them.
- **Reviewing changes locally before publishing** — use the pack's review
  workflow, which runs the deterministic checks the remote review assumes.
- **Anything with no pack wrapper** — use the underlying command directly.
  The pack adds surfaces; it does not replace the tools it wraps.

To see which wrappers this repository actually has, list the installed skills
rather than relying on a list written down somewhere: they are the pack's
`sd-*` skills, and the pack's own help surface enumerates them at runtime.

Nothing verifies or rewrites this block any more. The machine-scope installer
never edits a tracked repository file, `AGENTS.md` included, so what follows is
hand-maintained like the rest of the document. It deliberately names no
individual command: the block routes by intent, so there is nothing in it that a
change to the command set could make false.
<!-- SD-AI-COMMAND-PACK:ROUTING:END -->
