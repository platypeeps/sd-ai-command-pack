# Fix Documentation And Help-Text Accuracy Batch Design

## Overview

This task should correct confirmed docs/help drift introduced by installer
decomposition, newer workflows, and platform hook differences. It is
accuracy-only, not a README restructure.

## Proposal

Update `install.py --help` strings so `--force` names all
`FORCE_PRESERVED_TARGETS` and `--local-only` names the actual
`trellis init --yes --skip-existing --codex` invocation. Add or update a test
that pins the help text to the registry's preserved-target list so the help
cannot drift again.

Modernize `.trellis/spec/backend/manifest-and-filesystem.md` references from
`install.py` to the modules where symbols now live. Add a short contributor
pointer block to `AGENTS.md` outside managed markers, add `SECURITY.md`, fill
the README workflow enumeration, and update installed guide twins for the full
preserved-file list.

For `FIRST_REPLY_NOTICE`, make an explicit decision. Preferred default:
remove hardcoded locale-specific first replies or gate them behind a
repo/local configuration signal, then make Codex/Gemini/GitHub hooks
consistent.

## Boundaries And Non-Goals

Do not restructure the README or change product behavior beyond the
FIRST_REPLY_NOTICE decision.

## Affected Files

- `install.py`
- `tests/test_install_core.py` or help-text tests
- `.trellis/spec/backend/manifest-and-filesystem.md`
- `AGENTS.md`
- `SECURITY.md`
- `README.md`
- `docs/SD_AI_COMMAND_PACK.md` and `templates/docs/SD_AI_COMMAND_PACK.md`
- Relevant hook templates/root copies for FIRST_REPLY_NOTICE

## Risks And Edge Cases

Guide twins must stay byte-identical. Hook changes may affect shipped payload,
so bump/release gate implications should be considered if behavior changes.

## Validation

Run help-text tests, docs/path preflight, guide twin drift checks, and the pack
full-check with local AI reviewers disabled.
