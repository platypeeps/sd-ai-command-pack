# Fix documentation and help-text accuracy batch

## Goal

Clear the batch of confirmed low-severity documentation and help-text
inaccuracies surfaced by the 2026-07-09 deep review, so the CLI's own
self-documentation, the contributor entry points, and the spec references
match the post-decomposition code.

## Problem

Each item below is CONFIRMED against current code:

- **`install.py --help` omits the third force-preserved file.**
  `install.py:97-98` says `--force` preserves "`.prism/rules.json` and
  `.gito/config.toml`", but `installer/registry.py:482-486`
  (`FORCE_PRESERVED_TARGETS`) also lists `.github/PULL_REQUEST_TEMPLATE.md`.
  README:307-309 documents all three correctly — only the help string is stale.
- **`install.py --help` omits the always-passed `--codex` init flag.**
  `install.py:115` says local-only runs `trellis init --yes --skip-existing`,
  but `installer/localonly.py:113` always appends `--codex`. README:292 is correct.
- **Spec references still point at `install.py` for moved symbols.**
  `.trellis/spec/backend/manifest-and-filesystem.md` cites ~15 symbols
  (`load_manifest()`, `PackFile`, `validate_manifest()`, …) as living in
  `install.py`; they are defined in `installer/manifest.py` (install.py only
  re-exports). One reference (~line 386) was already modernized, confirming a
  partial update.
- **AGENTS.md gives agents no operating pointers.** It contains only the
  Trellis-managed block and two maintainer rules — no test command, no
  coverage/lint invocation, no link to CONTRIBUTING.md, the Makefile, or the
  two spec files that explain adding commands/manifest entries. An agent
  landing here discovers `make check` only by luck.
- **SECURITY.md absent.** No root or `.github/` copy, despite the repo
  shipping installer tooling that writes into target repos, provenance
  hashing, and a `requirements-security.txt` / bandit / zizmor lane.
- **README Overview enumeration omits the two newest workflows.**
  README:13-15 lists the workflows but not work-backlog or work-designs,
  though both have dedicated README sections further down.
- **Guide "Updating the pack" preserved-file list is incomplete (both twins).**
  `docs/SD_AI_COMMAND_PACK.md:1123-1126` (and its `templates/docs` twin)
  enumerates `.prism/rules.json` and `.gito/config.toml` as the preserved set,
  omitting `.github/PULL_REQUEST_TEMPLATE.md` (covered separately at guide
  lines 261-264 but reads as exhaustive here).
- **FIRST_REPLY_NOTICE intent (judgment call).** A hardcoded Chinese
  first-reply instruction ships in `.codex/hooks/session-start.py` and
  `.gemini/hooks/session-start.py` but not `.github/copilot/hooks/session-start.py`
  (and `systemMessage` exists only in the codex variant). Decide whether this
  is intended end-user behavior; if yes, gate it on a locale/config signal and
  make the three platforms consistent; if not, remove it.

## Requirements

- R1: `install.py` argparse help for `--force` names all three
  force-preserved targets; help for `--local-only` reflects the `--codex`
  flag actually passed.
- R2: The manifest-and-filesystem spec cites `installer/manifest.py` (and the
  correct module) for each symbol it references.
- R3: AGENTS.md gains a short contributor pointer block (CONTRIBUTING.md,
  `make check`, the two spec files) placed outside the Trellis-managed block.
- R4: A SECURITY.md is added (root or `.github/`) describing supported
  versions and how to report a vulnerability.
- R5: README Overview enumeration includes work-backlog and work-designs.
- R6: The guide's "Updating the pack" preserved-file enumeration lists all
  three preserved targets (both twins stay byte-identical).
- R7: FIRST_REPLY_NOTICE resolved per the decision above; the three
  session-start hooks are consistent with that decision.

## Acceptance Criteria

- [ ] `python3 install.py --help` names all three preserved files and the
      `--codex` flag; a parity/doc test pins the preserved-file list against
      `FORCE_PRESERVED_TARGETS` so it cannot drift again.
- [ ] No spec file cites `install.py` for a symbol that lives in `installer/*`.
- [ ] AGENTS.md routes an agent to CONTRIBUTING.md / `make check` / specs.
- [ ] SECURITY.md present.
- [ ] README + guide enumerations complete; docs twins byte-identical;
      review-preflight doc-path checker still passes.
- [ ] FIRST_REPLY_NOTICE decision applied and hooks consistent.

## Non-goals

- Restructuring the README or guide (done in PR #72). This is accuracy-only.
