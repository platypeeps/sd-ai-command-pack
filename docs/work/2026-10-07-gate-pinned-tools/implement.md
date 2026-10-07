# Implement — gate pinned tools

The design is in [design.md](design.md). One pull request in this repository;
sd:2937 follows in the system repository.

## Step checklist

- [x] 1. `bin/sd_gate_tools.py`: `PINS`, `folder`, `path_entries`, `missing`,
      `install`, `status`. Check: `tests/test_sd_gate_tools.py` passes, and
      each install test fails with its guard removed.
- [x] 2. `sd gate tools status|install` in `bin/sd`. Check: the verb tests
      pass; `sd gate tools status --json` on this machine lists three pins.
- [x] 3. `sd_gate_receipts`: pinned `PATH` in `offload_pins`, the refusal in
      `from_receipts`, the skip in `cargo_subcommands`, `resolution` and
      `system_version` in `view_tool`. Check: the gate tests pass, and each
      new one fails with its guard removed.
- [x] 4. Existing fixtures isolate `PINS` beside the real gate cache. Check:
      the offload suites pass unchanged in what they assert, but the two
      exact `resolution` dicts, which now hold every bound name.
- [x] 5. Docs: the offload design's tool section names the pins. Check:
      `sd-docs-lint` from the repository root passes.
- [x] 6. `sd gate check --base main`, then `sd-review --scope branch --gate-check main` (rounds 1 and 2).
- [x] 7. Round 3 (lead scope): bind `developer_tools`, name `macos_version`; CLT links for `git` and `make`;
      `uv` 0.12.23; refuse an archive that shadows a bound name; `cargo` resolution names its file.
      Check: each new test fails with its guard removed; the decision log in design.md names each choice.
- [ ] 8. `sd gate check --base main`, then `sd-review --scope branch --gate-check main` (round 3).
