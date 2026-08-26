# Status Collector Machine-Scope Resolution Implementation Plan

## Execution Order

1. **Reproduce first, in a test.** Add a fixture building the machine-install
   arrangement: collector at `<tmp>/bin/sd-ai-command-pack-status.py` as a real
   file (not a symlink), no `<tmp>/installer/`, and a separate trusted pack root
   whose `bin/` is injected into the fixture's `PATH`. Assert the engine
   resolves. **This test must fail on current `main`** — run it and see it fail
   before writing any resolver code. A reproduction that passes before the fix
   is testing something else.

2. **Extract the candidate-root helper.** In the canonical
   `templates/scripts/sd-ai-command-pack-status.py` — not `scripts/`, which is
   a generated mirror — add a private helper returning the
   ordered candidate roots — script-adjacent, then `path_pack_bins()` parents in
   `PATH` order. Two rungs only; `design.md` records why the drafted
   working-directory rung was dropped in review. Pure function of
   `(script path, environ)`; no import, no side effect. Test it directly for
   order.

3. **Add the trust gate.** A second private helper takes a candidate root and
   returns either acceptance or a typed refusal reason:
   - `installer/__init__.py` and `installer/machinescope.py` both exist as
     regular files — a real package, not a lone dropped module;
   - the root carries **either** `manifest.json` with `name`
     `sd-ai-command-pack` **or** `.claude-plugin/plugin.json` with `name` `sd`.
     Do not key on `manifest.json` alone: the plugin cache root this fix exists
     to reach carries none, so that gate would reject the target root and ship
     a fix that fixes nothing. `design.md` holds the measured table; assert
     **both** marker forms in tests;
   - none of root, `installer/`, or `machinescope.py` is world-writable
     (`stat.S_IWOTH`).
   Rung 1 bypasses the gate deliberately — it is the tree already executing, and
   gating it would make the collector refuse to run from a checkout the user
   already trusts enough to have invoked. State that in a comment; it is the
   kind of asymmetry a reviewer should not have to reconstruct.

4. **Rewire `machine_scope_api()`** (`:1717`) to walk the ladder: first accepted
   candidate wins, `sys.path` insertion and removal stay scoped exactly as today,
   and `suppress_bytecode_writes()` still wraps the import. Accumulate refusals.
   On exhaustion raise `RuntimeError` naming every candidate tried and each
   refusal reason. Return the module plus the root and rung that supplied it.

5. **Thread provenance into the report.** `machine_receipt_state()` (`:1817`)
   records `engineRoot`, `engineRung` (`adjacent` or `path`), and bounded
   `engineRefusals`;
   `format_machine_scope()` (`:3146`) renders root and rung only when the rung
   is not `adjacent`, so today's output is byte-identical in the common case.
   Apply `safe_text` limits, matching the file's existing convention.

6. **Update the docstring** on `machine_scope_api()`. Its current arrangement
   list ("`scripts/` in a pack checkout, `bin/` under a plugin root") is part of
   the defect: the machine install is a third arrangement it does not mention.

7. **Regenerate the mirrors.** Edit only `templates/scripts/`; then
   `make sync` (`install.py . --force`) followed by `make generate` produces
   `scripts/`, `plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/`.
   Never hand-edit a mirror. Confirm all four copies are byte-identical
   afterwards, and re-run the fleet candidate check if `surface-check` reports
   a stale `payloadDigest`.

8. **Changelog + version bump**, per the repo's release convention.

## Validation Plan

Focused, in order:

```bash
python3 -m unittest tests.test_status                  # unittest, not pytest
node scripts/sd-ai-command-pack-review-preflight.mjs  # expect 0 failures
make generate                                          # mirrors + surface closure
```

Then the broad repo gate warranted by a change to a shipped script.

Required assertions, each its own test:

- machine-install arrangement resolves (step 1 — must have failed pre-fix);
- pack-checkout and plugin-root arrangements resolve **through rung 1**,
  asserted on the *resolved path*, not on success alone;
- symlinked `~/.agents/bin` resolves through rung 1;
- decoy root on `PATH` carrying only `installer/machinescope.py` is refused;
- a root identified by `.claude-plugin/plugin.json` alone is **accepted** — the
  plugin cache arrangement, and the case a `manifest.json`-only gate breaks;
- world-writable candidate is refused;
- both refusals are *reported*, not swallowed into a bare `unavailable`;
- candidates are tried in `PATH` order;
- no-rung case raises and names every candidate;
- provenance renders when rung is not `adjacent`, and a fixture where engine
  root version differs from the reported install shows both;
- **end to end**: a `collect_machine_scope`-level test over the thin-consumer
  arrangement renders a real machine-scope row rather than `unavailable`,
  including the version-skew case #496 reports as hidden. The unit tests above
  prove the ladder resolves; only this one proves the row a reader actually
  sees changed, which is the acceptance criterion's own wording.

## Documentation And Spec Updates

- `machine_scope_api()` docstring (step 6).
- The `sd-help` pack-helper-resolution reference documents the *toolchain*
  ladder, which this change does not alter — confirm before editing, and do not
  conflate the two ladders. Update only if it makes a claim about engine
  resolution that this change falsifies.
- Changelog entry naming the arrangement that was broken.

## Review Notes

- The security gate is the reviewable core, not the ladder. Ask specifically:
  can a directory an unprivileged process controls end up supplying
  `machinescope.py`? Rung 2 is externally influenced; rung 1 is not.
- Rung 1 bypassing the gate is deliberate; if a reviewer reads it as an
  oversight, the comment in step 3 is not doing its job.
- Additive report keys must not break an older reader.

## Rollback Points

- After step 1: test only, nothing shipped.
- After step 6: canonical behavior complete, mirrors not yet regenerated —
  revert is a single-file revert.
- After step 7: revert the commit; no state, schema, or migration is involved.

## Follow-Ups (explicitly outside this PR)

- Whether the `sd-status` skill should route thin consumers to a different
  collector copy at all is issue #496's direction 2. This task fixes the loader;
  the routing question stays open and unowned.
- The machine payload shipping `installer/` (direction 3) is rejected in
  `design.md`; if that judgment is ever revisited it is a separate task.
