# Trellis Review PR Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/trellis-review-pr-pack)

Install reusable Trellis PR review, full-check, and post-merge housekeeping
workflows into
[Trellis-managed repositories](https://trytrellis.app/).

The pack includes:

- `.agents/skills/trellis-review-pr/SKILL.md`
- `.agents/skills/trellis-full-check/SKILL.md`
- `.agents/skills/trellis-housekeeping/SKILL.md`
- `scripts/trellis-full-check.sh`
- `scripts/trellis-housekeeping.sh`
- `.prism/rules.json`
- `docs/TRELLIS_REVIEW_PR_PACK.md`
- `.claude/commands/trellis/review-pr.md`
- `.claude/commands/trellis/full-check.md`
- `.claude/commands/trellis/housekeeping.md`
- `.gemini/commands/trellis/review-pr.toml`
- `.gemini/commands/trellis/full-check.toml`
- `.gemini/commands/trellis/housekeeping.toml`
- `.github/prompts/review-pr.prompt.md`
- `.github/prompts/full-check.prompt.md`
- `.github/prompts/housekeeping.prompt.md`
- `.opencode/commands/trellis/review-pr.md`
- `.opencode/commands/trellis/full-check.md`
- `.opencode/commands/trellis/housekeeping.md`

The shared skills own the workflows. Platform command and prompt files are thin
entry points that tell the agent to load the appropriate shared skill.
The installed `docs/TRELLIS_REVIEW_PR_PACK.md` file gives humans and agents a
repo-local usage guide for the commands, script, environment variables, local
Prism/Gito behavior, and troubleshooting steps.

`/trellis:full-check` is optional but strongly recommended before PR readiness.
It runs deterministic checks, then local Prism review when available. Gito stays
opt-in through `TRELLIS_FULL_CHECK_GITO=1` because it may invoke `uvx`, local
cache access, network access, and configured LLM credentials. When enabled,
Gito writes reports to `.build/review/gito` by default; override with
`TRELLIS_FULL_CHECK_GITO_OUT_DIR` when needed.

`/trellis:housekeeping` is for ending a single active development stream. If
the current feature branch has an open PR that is clean, green, comment-clean,
and exactly matches the local and remote branch heads, it can run
`trellis-finalize`, push the journal commit back to the PR branch with a
best-effort `[skip ci]` marker, merge the PR, and then continue into normal
post-merge cleanup. If that gate is not satisfied, it behaves as a post-merge
cleanup command: fetch/prune, confirm the current feature branch's PR is merged
and the local branch head matches that PR before deleting anything, switch to
the default branch, fast-forward it, remove the merged local and remote branch,
and finish with a condensed "expected clean state" plus anomalies report.

`/trellis:review-pr` is local-review-first. It runs the full-check/Prism path
before requesting a paid or remote GitHub Copilot review, and treats Copilot as
an explicit final pass rather than the default convergence mechanism.
If an active review-pr session observes that the PR is `MERGED`, it stops the
review loop and runs `/trellis:housekeeping` automatically. This is session
automation, not a background webhook; it cannot wake an inactive tool session.

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
left untouched. Use `--force` to overwrite them. Add `--backup` with `--force`
to save overwritten files next to the original with a `.bak` suffix.

Platform filters always include the shared skills, full-check and housekeeping
scripts, Prism rules, and usage guide, because every adapter delegates to the
shared workflow.

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

This pack is intentionally shaped like the eventual Trellis upstream change:

- Move the shared skill to
  `packages/cli/src/templates/common/bundled-skills/trellis-review-pr/SKILL.md`.
- Move the full-check skill and script to the equivalent shared template
  locations.
- Move the housekeeping skill and script to the equivalent shared template
  locations.
- Move command templates into Trellis' common or platform-specific command
  template directories.
- Add template distribution tests and package verification in the Trellis CLI
  repo.
