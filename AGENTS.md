# sd-ai-command-pack

Instructions for AI assistants working in this repository.

## Maintainer Rules

- Follow [.claude/rules/sd-operator-defaults.md](.claude/rules/sd-operator-defaults.md) for reviewer selection and report content.
  These defaults apply to both Claude and Codex.
  Writing style and diagram tooling come from each agent's global instructions.
- Merge permission is one setting, `repo.runner_merge` on the repository row (`bin/sd-db repo list`, last field).
  `auto`: merge active, in-scope PR work without asking, through `sd-ship prepare` then `sd-ship merge`,
  unless the user says wait. `manual` or no row: ask the operator first.
  No value permits a merge that skips `sd-ship`, such as `gh pr merge` or a web squash; an `sd-ship` refusal is a stop.
- Reject a review finding with a reason note a reader can check; a rebuttal needs no operator acceptance.
- Ask the operator before adding a command, flag, config key, state store, gate, check, file kind or document type; name what it replaces, and prefer deleting or reusing.
- Record decisions, incidents and findings in sd notes, not in new `docs/` files.
- Do not create pull requests in the upstream `Trellis` repository without
  explicit approval from the user for that specific upstream PR. If
  `sd-ai-command-pack` work uncovers a `Trellis`-owned change, document the
  finding and provide a paste-ready handoff instead of opening a `Trellis` PR.
- At the planning convergence boundary, follow
  [.claude/rules/sd-planning-adversarial-review.md](.claude/rules/sd-planning-adversarial-review.md).
  That file holds the rule and the review table every review point reads its cap from.
- Before dispatching a worker or opening a second checkout, follow
  [WORKFLOW.md § Parallel work](WORKFLOW.md#parallel-work).
- `skills/**` holds the one copy of the payload; nothing renders into this repository.

## Companion Repository Scope

Work started here may also change these companion repositories:

- `/Users/example/repos/platypeeps/sd-writing`
- `/Users/example/repos/system`

Treat related implementation, tests, documentation, CI, and coordinated delivery in these repositories as part of this project's scope.
Do not request confirmation solely because an in-scope operation targets either companion repository.
Read each repository's instructions and preserve its existing work before making changes.
This scope exception does not authorize unrelated work or remove specific approval requirements for destructive actions or upstream Trellis PRs.
External review uses the operator's standing machine policy, with local restrictions and existing spending limits.
Read `sd config get sd.external_reviews`; installation never grants it.
Every other `sd.*` setting grants nothing; `WORKFLOW.md` § Standing authorization lists them.
Shared contributors do not revoke merge permission; ownership gates still apply.

## Contributor Entry Points

- Read [CONTRIBUTING.md](CONTRIBUTING.md), then run `make check` before
  publishing a change.
- Read [docs/current-architecture.md](docs/current-architecture.md) before changing the installer or command set.
- Read each `docs/spec/**` notice before using that page.
  Some pages describe the retired pre-3e model.
- Work items are rows (`sd task add`). [docs/work](docs/work/README.md) holds one directory per
  item whose shape needs agreement, with a single `design.md`.

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

## When the Git Wrapper Is Refused

- In a worktree-isolated session the guard refuses the hook's wrapped `git`; call `/usr/bin/git` and say so in the report.
- Never edit the wrapper's exclusion list to pass that refusal: the list is machine-global, the refusal per-session.

## Area Rules

Claude loads each file for its `paths:`, or always when it has none; Codex reads them by link.

| Topic | File |
| --- | --- |
| Reviewer selection and report content | [.claude/rules/sd-operator-defaults.md](.claude/rules/sd-operator-defaults.md) |
| Planning adversarial review and its caps | [.claude/rules/sd-planning-adversarial-review.md](.claude/rules/sd-planning-adversarial-review.md) |
| What a document owns: live text, archives, qualified paths | [.claude/rules/document-scope.md](.claude/rules/document-scope.md) |
| Where a finished document goes: vault, dashboard, mirrors | [.claude/rules/publication.md](.claude/rules/publication.md) |

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

Nothing verifies or rewrites this block; it is hand-maintained. It names no
individual command, so a change to the command set cannot make it false.
<!-- SD-AI-COMMAND-PACK:ROUTING:END -->
