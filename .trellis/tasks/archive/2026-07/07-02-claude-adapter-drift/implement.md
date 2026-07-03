# Implementation plan: claude adapter drift fixes

Branch: `claude-adapter-drift` off `main`.

## Checklist

1. [ ] install.py: `read_existing_installed_targets` + preservation wiring
       in the main flow + `kept-in-receipt` reporting (D1).
2. [ ] Audit template + installed twin: gitignore-aware missing-target
       classification (D2).
3. [ ] Claude adapter templates (start/continue/finish-work) + installed
       twins under `.claude/commands/sd/` (D3).
4. [ ] Tests T1–T6 plus any template-content test updates (D4).
5. [ ] Docs paragraphs + `manifest.json` 0.5.9 (D5).
6. [ ] Validation gates (below), then commit and PR.

## Validation

- `python3 -m pytest tests/ -q` — full suite green, coverage gate holds.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0
  bash scripts/sd-ai-command-pack-full-check.sh` — includes the template-twin
  drift gate and env-var doc gate.
- Manual spot-check: dry-run install into a scratch clone shaped like
  anomaly-metric-creator (receipt with claude entries, no markers) shows
  `kept-in-receipt` lines and an unchanged receipt.

## Review gates / rollback points

- After step 4: all tests green before touching docs/version.
- PR review is the final gate; no auto-merge.
