# Trellis Review PR Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/trellis-review-pr-pack)

Install a reusable Trellis PR review loop into
[Trellis-managed repositories](https://trytrellis.app/).

The pack includes:

- `.agents/skills/trellis-review-pr/SKILL.md`
- `.gemini/commands/trellis/review-pr.toml`
- `.github/prompts/review-pr.prompt.md`
- `.opencode/commands/trellis/review-pr.md`

The shared skill owns the workflow. Platform command and prompt files are thin
entry points that tell the agent to load the shared skill.

## Install

From this repository:

```bash
python3 install.py /path/to/trellis/repo
```

The installer requires `.trellis/config.yaml` in the target repo. It always
installs the shared `.agents` skill and installs platform adapters only when the
target repo already has the corresponding platform directory.

Useful options:

```bash
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform gemini --platform github
python3 install.py /path/to/repo --force
```

By default, existing files with different content are reported as conflicts and
left untouched. Use `--force` to overwrite them.

## Verify

The installer runs `git diff --check` in the target repo unless
`--skip-diff-check` is passed.

Run the pack tests with:

```bash
python3 -m unittest discover -s tests
```

## Supported Adapters

| Platform | Installed When |
| --- | --- |
| Shared skill | Always |
| Gemini CLI | `.gemini/` exists, or `--all` / `--platform gemini` |
| GitHub Copilot | `.github/` exists, or `--all` / `--platform github` |
| OpenCode | `.opencode/` exists, or `--all` / `--platform opencode` |

## Upstream Path

This pack is intentionally shaped like the eventual Trellis upstream change:

- Move the shared skill to
  `packages/cli/src/templates/common/bundled-skills/trellis-review-pr/SKILL.md`.
- Move command templates into Trellis' common or platform-specific command
  template directories.
- Add template distribution tests and package verification in the Trellis CLI
  repo.
