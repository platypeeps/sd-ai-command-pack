# Add Distributed Toolchain Preflight

## Goal

Give SD workflows one conservative, reusable way to resolve supported local
tools, identify the repository's established check surfaces, and fail once with
an actionable remedy instead of running avoidable fallback commands.

## Background

- A focused test in this repository first ran under Apple/Xcode Python 3.9,
  which lacked project dependencies, then under unversioned Homebrew Python
  3.14, which also lacked them. The repository's `Makefile` already selects
  Homebrew Python 3.13 and `.venv`; the ad hoc command bypassed that contract.
- Distributed docs recommend Homebrew Python on macOS, but they do not enforce
  interpreter precedence or reject an unsupported/missing-dependency runtime.
- `sd-ai-command-pack-full-check.sh` validates pack/review integration but does
  not necessarily run the target repository's canonical unit-test or lint
  command. A successful pack gate must not imply that project checks ran.
- Sandboxed agent sessions repeatedly allow direct Git operations while nested
  `git add` / `git commit` calls inside Python wrappers fail on `.git/index.lock`.
- The framework is tool-agnostic. Generic discovery must not assume every
  target is a Python, Node, Make, or GitHub project.

## Requirements

- **R1: Explicit tool resolution.** Add a distributed pack-owned preflight
  helper that resolves a Python interpreter and reports other relevant tool
  capabilities without modifying the repository or installing dependencies.
- **R2: Python precedence.** Resolve Python in this order:
  `SD_AI_COMMAND_PACK_PYTHON`, repo `.venv` (`bin/python` or
  `Scripts/python.exe`), active `VIRTUAL_ENV`, versioned Homebrew Python 3.13 on
  macOS, then a supported `python3` on `PATH`.
- **R3: Validate once.** Verify the selected interpreter's minimum supported
  version and any caller-specified modules before executing the requested
  command. If the highest-precedence repo environment exists but is invalid,
  stop with its exact path and setup remedy; do not silently try multiple
  interpreters with inconsistent dependencies.
- **R4: Canonical project checks.** Support an explicit
  `SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND`. When unset, report exact existing
  check candidates from established repo infrastructure, but do not execute an
  inferred or ambiguous command. SD workflows must state separately whether
  project checks and the pack full-check ran.
- **R5: Conservative discovery.** Recognize only explicit Makefile targets,
  package scripts, or executable repo scripts with conventional check names.
  Never infer commands from incidental prose, and never recurse from a project
  `check` command back into the pack full-check.
- **R6: Sandbox-aware execution.** Document and adopt no-nested-Git variants
  where pack wrappers support them, such as recording a session with
  `--no-commit` followed by explicit agent-owned Git operations. Continue using
  temp-backed cache defaults for Python, uv, Ruff, Prism, and Gito.
- **R7: Resolve/probe/execute/verify.** Distributed workflow guidance must
  resolve a tool, probe version/capability, execute once, and verify the
  observable result. A command exit status alone is insufficient for remote or
  asynchronous effects.
- **R8: Ownership boundaries.** Change only pack-owned templates, scripts,
  skills, docs, installer metadata, and tests. Do not modify original
  Trellis-owned runtime, skills, or generated platform files directly.
- **R9: Shipped consistency.** Install the helper in consumer repos, keep
  template/root mirrors synchronized, document overrides and precedence, bump
  the pack version, and cover supported platform/path variants.

## Acceptance Criteria

- [ ] A deterministic helper selects the documented Python candidate order and
      prints the selected path/version.
- [ ] Tests cover repo `.venv`, Windows-style `.venv/Scripts/python.exe`, active
      virtualenv, Apple Silicon and Intel Homebrew 3.13, supported PATH Python,
      unsupported Python, missing modules, and explicit override behavior.
- [ ] A present but invalid repo `.venv` fails once with `make setup` or the
      repository's documented setup remedy; no extra interpreter run occurs.
- [ ] `doctor` output distinguishes project-check candidates, selected explicit
      project check, pack full-check, optional tools, and sandbox cache state.
- [ ] `sd-review-pr` and `sd-create-pr` report project checks separately from
      the deterministic pack gate and use the preflight before direct Python
      validation commands.
- [ ] Pack-owned finish-work guidance avoids nested Git writes in sandboxed
      sessions when a no-commit path exists.
- [ ] No helper auto-installs tools, mutates shell startup files, guesses an
      ambiguous project check, or edits Trellis-owned files.
- [ ] Installer, removal, provenance, audit, root/template parity, KB freshness,
      and full test/coverage gates pass.

## Out Of Scope

- Installing or upgrading Python, Node, GitHub CLI, Prism, Gito, or project
  dependencies automatically.
- Replacing target-repository package managers, virtualenv conventions, or CI.
- Making the pack full-check execute arbitrary discovered shell prose.
- Changing upstream Trellis commands or skills.
