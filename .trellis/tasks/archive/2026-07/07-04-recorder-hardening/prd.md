# Recorder hardening for fleet Trellis variants

## Goal

Fix the four defects the 0.5.16 fleet refresh reviews surfaced in
`templates/scripts/sd-ai-command-pack-record-session.py`, bump the pack to
0.5.17, and fold the fix into the six open refresh PRs.

## Background

- mezmo_benchmark's preflight gate 8 (defect-patterns) fails PR #317:
  three text-mode `subprocess.run` calls and one `Path.write_text` lack
  explicit `encoding=`/`errors=`, pinning decodes to the host locale.
- anomaly-metric-creator #194: duplicate hashes in `--commit` are silently
  de-duplicated by the subjects dict, leaving an unpatched
  `(see git log)` row and a confusing late failure.
- rwbp-coordinator #77: an option-like value (`--all`) passed as a commit
  hash is parsed by `git log` as an option instead of being rejected.
- loadsmith #50: their Trellis `add_session.py` already resolves commit
  subjects (`git show -s --format=%s --end-of-options`, line 173) and
  seeds `- Validation not recorded for this session.` as the Testing
  default (line 183), so the wrapper's `(see git log)` /
  `- [OK] (Add test results)` anchors do not exist and the wrapper is
  unusable there.

## Requirements

- R1: Every text-mode subprocess call and text write in the recorder pins
  `encoding="utf-8"` and an explicit `errors=` policy (replace for git
  output reads, strict for files the wrapper writes).
- R2: `--commit` validation fails fast (exit 2) on duplicate hashes and on
  option-like values starting with `-`; the git subject lookup passes
  `--end-of-options` as defense in depth.
- R3: The patcher tolerates Trellis variants: commit-table rows are
  overwritten via hash-anchored row match whether the seeded cell is a
  placeholder or a pre-resolved subject, and the Testing (and, when
  requested, Next Steps) section body is replaced wholesale between
  headings instead of anchoring on version-specific placeholder strings.
- R4: New behavior is covered by tests: duplicate/option-like hash
  rejection, and an add_session variant that pre-fills subjects and seeds
  the loadsmith Testing default.

## Acceptance criteria

- [x] `run_git`, both remaining `subprocess.run` calls, the journal
  `write_text`, and the content tempfile carry explicit encoding and
  errors policies, so mezmo gate 8 passes on the folded-forward PR.
- [x] `--commit a,a` and `--commit=--all` exit 2 with clear messages
  before any journal is touched.
- [x] The wrapper completes end-to-end against an add_session variant
  that pre-fills commit subjects and uses the
  `- Validation not recorded for this session.` Testing default.
- [x] Full battery green: 258+ tests, 100% coverage on install.py,
  full-check (template twin byte-identical), shellcheck.
- [x] 0.5.17 folded into the six open fleet refresh PRs (post-merge
  step).

## Reconciliation Note - 2026-07-09

Reconciled by `07-06-close-fleet-refresh-loop`: Session 26 records the
0.5.17 implementation as shipped, and the hardening is folded into the
current `0.7.0` payload that audits clean across all five actual consumer
repositories.
