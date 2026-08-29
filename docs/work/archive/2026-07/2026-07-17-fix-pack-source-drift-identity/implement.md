# Implementation Plan

1. Extend `test_pack_source_drift_gate_skips_se_pack_identity` with explicit
   assertions that the drift body did not emit environment-variable scan output
   or stale-variable diagnostics.
2. Run the focused `tests.test_pack_drift` module through the repository
   toolchain.
3. Confirm the template and installed full-check scripts remain byte-identical.
4. Run the deterministic full-check with Prism and Gito disabled.
5. Reassess release metadata: keep version `0.16.2` when only tests and Trellis
   task records changed; invoke the release ledger only if payload changes.
6. Report that the observed SE checkout is installed at `0.15.6` and requires a
   normal provenance-managed refresh, without editing that checkout here.
