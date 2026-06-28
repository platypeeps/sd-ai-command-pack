# Trellis Review PR Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/trellis-review-pr-pack)

Install reusable Trellis continue, finish-work, PR review, full-check,
post-merge housekeeping, and refresh-specs wrapper workflows into
[Trellis-managed repositories](https://trytrellis.app/).

The pack includes:

- `.agents/skills/trellis-review-pr/SKILL.md`
- `.agents/skills/trellis-full-check/SKILL.md`
- `.agents/skills/trellis-housekeeping/SKILL.md`
- `scripts/trellis-full-check.sh`
- `scripts/trellis-housekeeping.sh`
- `.prism/rules.json`
- `docs/TRELLIS_REVIEW_PR_PACK.md`
- `.claude/commands/sd/continue.md`
- `.claude/commands/sd/finish-work.md`
- `.claude/commands/sd/full-check.md`
- `.claude/commands/sd/housekeeping.md`
- `.claude/commands/sd/refresh-specs.md`
- `.claude/commands/sd/review-pr.md`
- `.gemini/commands/sd/continue.toml`
- `.gemini/commands/sd/finish-work.toml`
- `.gemini/commands/sd/review-pr.toml`
- `.gemini/commands/sd/full-check.toml`
- `.gemini/commands/sd/housekeeping.toml`
- `.gemini/commands/sd/refresh-specs.toml`
- `.github/prompts/sd-continue.prompt.md`
- `.github/prompts/sd-finish-work.prompt.md`
- `.github/prompts/sd-review-pr.prompt.md`
- `.github/prompts/sd-full-check.prompt.md`
- `.github/prompts/sd-housekeeping.prompt.md`
- `.github/prompts/sd-refresh-specs.prompt.md`
- `.opencode/commands/sd/continue.md`
- `.opencode/commands/sd/finish-work.md`
- `.opencode/commands/sd/review-pr.md`
- `.opencode/commands/sd/full-check.md`
- `.opencode/commands/sd/housekeeping.md`
- `.opencode/commands/sd/refresh-specs.md`

The shared skills own the workflows. Platform command and prompt files are thin
entry points that tell the agent to load the appropriate shared skill.
User-facing command adapters live under the `sd` namespace so pack-owned
wrappers do not collide with Trellis-owned generated `/trellis:*` commands on
future `trellis update` runs. GitHub Copilot prompt files use the equivalent
`sd-<command>` filename prefix.
The refresh-specs wrapper runs the Trellis-provided `trellis-update-spec` skill
as-is, refreshes repo-owned repospec artifacts through existing maintenance
infrastructure when available, then adds an explicit architectural-overview
check.
The continue and finish-work wrappers similarly delegate to Trellis-provided
`trellis-continue` and `trellis-finish-work` skills without changing their
behavior.
The installed `docs/TRELLIS_REVIEW_PR_PACK.md` file gives humans and agents a
repo-local usage guide for the commands, script, environment variables, local
Prism/Gito behavior, and troubleshooting steps.

`/sd:full-check` is optional but strongly recommended before PR readiness.
It runs deterministic checks, then local Prism review when available. Gito stays
opt-in through `TRELLIS_FULL_CHECK_GITO=1` because it may invoke `uvx`, local
cache access, network access, and configured LLM credentials. When enabled,
Gito writes reports to `.build/review/gito` by default; override with
`TRELLIS_FULL_CHECK_GITO_OUT_DIR` when needed.

`/sd:continue` and `/sd:finish-work` are local namespace aliases for the
Trellis-provided `trellis-continue` and `trellis-finish-work` skills. They
exist so day-to-day Trellis entry points can be invoked through the same `sd`
command namespace as the pack workflows.

`/sd:housekeeping` is for ending a single active development stream. If
the current feature branch has an open PR that is clean, green, comment-clean,
and exactly matches the local and remote branch heads, it can run
`trellis-finalize`, push the journal commit back to the PR branch with a
best-effort `[skip ci]` marker, merge the PR, and then continue into normal
post-merge cleanup. If that gate is not satisfied, it behaves as a post-merge
cleanup command: fetch/prune, confirm the current feature branch's PR is merged
and the local branch head matches that PR before deleting anything, switch to
the default branch, fast-forward it, remove the merged local and remote branch,
and finish with a condensed "expected clean state" plus anomalies report.

`/sd:review-pr` is local-review-first. It runs the full-check/Prism path
before requesting a paid or remote GitHub Copilot review, and treats Copilot as
an explicit final pass rather than the default convergence mechanism.
If an active review-pr session observes that the PR is `MERGED`, it stops the
review loop and runs `/sd:housekeeping` automatically. This is session
automation, not a background webhook; it cannot wake an inactive tool session.

`/sd:refresh-specs` runs the existing Trellis `trellis-update-spec` skill
without modifying or replacing it. After the update-spec pass, it checks whether
the repo has checked-in infrastructure for maintaining a repospec artifact, such
as repo docs, scripts, package tasks, or make targets. When that infrastructure
exists, the command uses it to refresh the repospec artifact instead of
hand-editing generated output. If that refresh uses Repomix, the output map
must be `docs/repomix-map.md`. It then checks whether the repo already has an
architectural overview such as `ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, or a
`.trellis/spec/**/architecture*.md` document. It updates that overview only
when the completed work changes high-level architecture; otherwise it reports
`not present` or `not warranted` without creating a new overview.

## Install

From this repository:

```bash
python3 install.py /path/to/trellis/repo
```

The installer requires `.trellis/config.yaml` in the target repo. It always
installs the shared `.agents` skills, full-check and housekeeping scripts,
Prism rules, and usage guide. It installs platform adapters only when the
target repo already has the corresponding platform directory.

Useful options:

```bash
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform gemini --platform github
python3 install.py /path/to/repo --force
python3 install.py /path/to/repo --force --backup
```

By default, existing files with different content are reported as conflicts and
left untouched. Use `--force` to overwrite them. The exception is an existing
`.prism/rules.json`: once it differs from the pack template, it is reported as
`preserved` and is never overwritten or reported as a conflict. Add `--backup`
with `--force` to save overwritten files next to the original with a `.bak`
suffix.
When installing the `sd` adapters, the installer also removes old
pack-generated `/trellis:*` adapter files when their content still matches the
pack templates. Legacy adapter files with other content are reported as
conflicts unless `--force` is supplied; with `--force`, they are removed while
the `sd` replacement is installed.

Platform filters always include the shared skills, full-check and housekeeping
scripts, Prism rules, and usage guide, because the review, full-check, and
housekeeping adapters delegate to those shared assets. The refresh-specs
adapter delegates to the Trellis-provided `trellis-update-spec` skill in the
target repo.

## Verify

The installer runs `git diff --check` on installed pack paths unless
`--skip-diff-check` is passed.

Run the pack tests with:

```bash
python3 -m unittest discover -s tests
```

## Supported Adapters

| Platform | Installed When |
| --- | --- |
| Shared skills, scripts, Prism rules, usage guide | Always |
| Claude Code | `.claude/` exists, or `--all` / `--platform claude` |
| Gemini CLI | `.gemini/` exists, or `--all` / `--platform gemini` |
| GitHub Copilot | `.github/` exists, or `--all` / `--platform github` |
| OpenCode | `.opencode/` exists, or `--all` / `--platform opencode` |

## Upstream Path

This pack is intentionally shaped so pieces could move upstream later, while
the local command namespace stays pack-owned:

- Move the shared skill to
  `packages/cli/src/templates/common/bundled-skills/trellis-review-pr/SKILL.md`.
- Move the full-check skill and script to the equivalent shared template
  locations.
- Move the housekeeping skill and script to the equivalent shared template
  locations.
- Move command behavior into Trellis' common or platform-specific command
  templates only if Trellis intentionally adopts those workflows; otherwise
  keep local wrappers under the pack-owned `sd` namespace.
- Add template distribution tests and package verification in the Trellis CLI
  repo.
