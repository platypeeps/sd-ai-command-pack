# Implement — vendored pack-source findings fix (0.64.1)

Branch off `main`. All shipped-script edits go in BOTH `scripts/` and
`templates/scripts/`, kept byte-identical.

## Phase A — re-verify (gate before any edit)

For each finding, read current HEAD and classify confirmed / already-resolved,
recording file:line:

- [ ] recovery-artifacts.py: list every genuinely empty, pass-only
  `except` (L202/207/211 + `_CleanupLock` blocks). Confirm read_text L216/L969
  already pass `encoding="utf-8"` (so the `errors=` finding is moot) and decide
  rebut-vs-harden per §2 of design.
- [ ] work-loop.py: empty except L1143-1144; read_text L2293 (already utf-8).
- [ ] update-spec-kb.py: **L553** full-file `read_bytes` (not L555).
- [ ] status.py: whether `classify_repository` stamps a `schemaVersion` (drives
  fix #4); whether the import guard can be symlinked in a real install.
- [ ] Confirm review-scope.sh needs NO change (already fixed): the provided-body
  check is at **L189-190** (L199 is blank) — record it.
- [ ] Write the confirmed/resolved table into the task research notes.

Validation: `grep`/`sed` evidence pasted per line. Any finding that turns out
already-fixed is dropped, not "fixed."

## Phase B — apply fixes (confirmed only)

- [ ] recovery-artifacts.py: replace empty pass-only handlers with
  `contextlib.suppress(<Exc>)` (structural — a comment does NOT clear CodeQL).
  For read_text: per §2 decision, either leave as-is (rebut) or add
  `UnicodeError` handling; do NOT add `errors="strict"` (no-op).
- [ ] work-loop.py: same structural `suppress` for L1143-1144; read_text per §2.
- [ ] update-spec-kb.py: bounded tail read in `file_ends_with_kb_copy_marker`
  (L553), with short-file guard; keep `except OSError: return False`.
- [ ] status.py: `schemaVersion == SCHEMA_VERSION` fail-closed check in
  `collect_recovery` (schemaVersion is stamped, so validate it directly — no
  required-keys fallback); symlink-reject on the import guard (both L800 and
  L1196), mirroring the L492-494 idiom.
- [ ] Mirror every edit into the other tree; `diff -r` the four files to prove
  byte-identity.

Validation after each file: `python3 -c "import ast; ast.parse(open(F).read())"`
and `diff scripts/F templates/scripts/F` → empty.

## Phase C — tests

Per-file coverage floors (76 overall; 80/80/83/80 for the four scripts) do NOT
force new-branch tests, so add them explicitly for correctness — and to avoid
dragging a file below its floor.

- [ ] update-spec tail-read: marker present / absent / file shorter than marker.
- [ ] status.py: schemaVersion mismatch → `status: invalid`; symlinked helper →
  unavailable/invalid.
- [ ] recovery-artifacts / work-loop: if §2 chose to harden, an invalid-UTF-8
  input test proving graceful handling (no unhandled `UnicodeError`).
- [ ] Run `make test`; confirm 0 skips, the install/installer 100% gate holds,
  and every per-file floor in `check-shipped-script-coverage.sh` still passes.

Validation: `make test` exits 0; `check-shipped-script-coverage.sh` passes with
each edited script at/above its floor.

## Phase D — release 0.64.1

Order matters: `prepare-release.py` validates that both `manifest.json.version`
and the top `CHANGELOG.md` heading were updated when the payload changed — do
both edits BEFORE `make release-prep`.

- [ ] Edit `manifest.json` `version` 0.64.0 → **0.64.1** (source of truth;
  `manifest.json.files[]` is routing metadata and does not change — no files
  added/removed).
- [ ] Add the top `CHANGELOG.md` heading + entry for 0.64.1.
- [ ] `make generate` (command surfaces + surface-check clean).
- [ ] `make sync` (dogfood reinstall from `templates/` + KB refresh; this
  regenerates the SHA-256 hashes in `.sd-ai-command-pack/provenance.json` for
  the edited scripts); confirm `install.py --status --audit .` reports 0.64.1
  current, audit passed, 0 drift.
- [ ] `make release-prep` — `prepare-release.py` (version + changelog gate,
  fleet evidence) then `make check`.

Validation: `make release-prep` exits 0; `git status` shows only intended files;
`manifest.json` version == 0.64.1; `.sd-ai-command-pack/provenance.json` hashes
match the edited scripts.

## Phase E — ship

- [ ] Commit (single logical commit or small stack), push, open PR.
- [ ] Request Copilot review; the same reviewers that raised these should now
  find the vendored callsites clean.
- [ ] Resolve/rebut review threads; merge to `main` green.
- [ ] Do NOT run fleet-refresh (fanout deferred per PRD).

## Review gates

- End of Phase A: confirmed-findings table exists; no edits started before it.
- Before Phase D: all fixes twinned + tests green (behavior-preserving proof).
- Before merge: `make check` green, manifest/provenance consistent at 0.64.1.

## Rollback points

- Abandon branch any time before merge (no consumer impact).
- If any single fix proves risky under the gate, drop just that fix and ship the
  rest; each finding is independent. (schemaVersion is confirmed stamped, so
  fix #4 validates it directly — no required-keys fallback.)
