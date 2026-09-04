---
title: implement — the cap first, then the boundary
status: planning
created: 2026-09-04
---

# Implement

Two pull requests, in order. The first cannot touch `dashboard/`; the second is
rebased on it.

## PR 1 — R11-D30, re-derive `DASHBOARD_CAP`

**Touches:** `tests/test_loc_caps.py`, and this item's own planning artifacts
under `docs/work/`. The invariant is not "one file" — it is **nothing under
`dashboard/`**, which is what makes this change fit beneath the ceiling it
replaces. Documentation does not charge `DASHBOARD_CAP`, and the planning
artifacts have to land somewhere; putting them in a third pull request would be
ceremony, not isolation.

`DASHBOARD_CAP` 4,350 → 4,375, with the itemisation from `design.md` written
into the comment above it in the form R11-D24 and R11-D29 use. The existing
paragraph about the archive-failure window stays; this appends the next
derivation rather than replacing the record of the last one.

`DASHBOARD_CODE_CAP` is not touched. It is downward-only under R11-D24, the fix
measures +2 against 31 lines of headroom, and a change that does not need it
does not get to move it.

**Why it is its own PR.** `test_loc_caps.py`'s docstring: *"a cap is never
raised in the PR that busts it"*, each re-derivation landing *"in its own
decision record by a change that fit under the ceiling it replaced"*. This PR
leaves `dashboard/` at 4,348 and therefore passes the 4,350 it is replacing —
which is the property that makes it legitimate, and is asserted below rather
than asserted about.

**Verification.**

- `make check` green, with `dashboard/` measuring 4,348 — unchanged by this PR.
- `git diff --name-only main` lists nothing under `dashboard/`. Not "exactly one
  file", which is what this bullet said until review pointed out that the PR
  deliberately carries the planning artifacts too. The single-file phrasing was
  left over from the scope sentence above it, corrected in the same change —
  which is the third time in this item that fixing a claim in one place left the
  same claim standing in another, and the reason the ledger's C-8 exists.

## PR 2 — the boundary

**Touches:** `dashboard/server.py`, `tests/test_dashboard_actions.py` (or
`tests/test_sd_ledger.py`, wherever the pairing tests land — see below).

The whole replacement body, pinned here rather than described, because the
+18 that `DASHBOARD_CAP` was re-derived from is a measurement *of this text*.
A patch that paraphrases it is a different measurement and invalidates R11-D30:

```python
def host_name(header: str | None) -> str:
    """The host out of a `Host` header, port removed, lowercased.

    Split out of `host_ok` when a second caller appeared and got it wrong.
    `[::1]:8767` has three colons and only the one after `]` is the port, so
    `split(":")[0]` yields `[` -- which is not a loopback name, so the IPv6
    loopback the server explicitly supports was recorded as tailnet demand.
    One parser, two callers, no second chance to disagree.

    A header this cannot parse is returned unparsed rather than repaired. The
    bracketed branch used to end `+ "]"`, and `partition` yields the whole
    string when the separator is absent, so `[::1` came back as `[::1]` -- a
    closing bracket the header never carried. `[::1]evil.com` came back the
    same way, and so did every other `[::1]<anything>`: an unbounded family
    admitted as the loopback, not a list of cases. No allow-list holds an
    unparsed header, so `host_ok` refuses it and `tailnet_host` records what
    arrived; returning `""` would land in `LOOPBACK_NAMES` instead and file a
    malformed header as local.
    """
    if not header:
        return ""
    name = header.strip().lower()
    if name.startswith("["):
        # `[addr]` or `[addr]:digits`, or it is not parsed at all. A colon
        # alone does not bound this -- it admits `[::1]:<anything>`, the same
        # unbounded family wearing a port.
        address, bracket, port = name.partition("]")
        return address + bracket if bracket and (
            not port or (port[0] == ":" and port[1:].isdigit())) else name
    if name.count(":") == 1:
        # Unbracketed repairs nothing to begin with: one colon is a port and
        # is dropped, anything else returns whole. `localhost:evil` yields
        # `localhost`, which is the host that was actually asked for.
        return name.rsplit(":", 1)[0]
    return name
```

`host_name` is 17 lines today (`dashboard/server.py:190-206`) and 35 after,
measured at **+18 total, +2 code**, landing at 4,366 / 2,271.

**Where the tests go.** `host_ok` behaviour is already tested in
`tests/test_dashboard_actions.py::Hosts`, and `host_name` classification in
`tests/test_sd_ledger.py::HostClassification` — the split follows the two
callers rather than the one function. The new cases assert both together, which
belongs with neither exclusively. They go in `Hosts`, because the refusal is the
security property and `Hosts` is where a reader looks for it, with
`HostClassification` gaining the single `tailnet_host` case that pins criterion
3. Recorded because splitting them the other way would also have been defensible
and the reason should not have to be reconstructed.

**The refusal table becomes the test.** Every row of `design.md`'s table, as
data, asserting `host_name` and `host_ok` in the same case so the two callers
cannot drift apart again.

**Verification, named before the work:**

1. `make check`, not direct invocation. `tests/test_sd_dashboard.py` is the one
   test file of the five touching this area with no `unittest.main()` guard:
   running it directly exits 0 having executed nothing, so a per-file loop
   reports a pass it never earned. Verified — it prints zero lines and returns 0
   on a clean tree. The two files that do carry `Host` assertions
   (`test_dashboard_actions.py`, `test_sd_ledger.py`) do have the guard and were
   both run green against the patched parser during design.
2. The seven existing accepted headers still pass (`127.0.0.1`,
   `127.0.0.1:8767`, `localhost:8768`, `[::1]:8767`, `tg-sol:8767`,
   `100.82.165.108:8767`, `[fd7a::1]:8767`), none of which the digits rule
   refuses. Any of them failing means the fix over-tightened.
3. Four mutations applied to `dashboard/server.py`, each required to produce a
   failure — the list in `design.md`. A mutation that survives is a test that
   does not test.
4. `dashboard/` measures 4,366 against the 4,375 from PR 1.
5. `__pycache__` cleared between mutation runs. A stale `.pyc` whose header
   matches the restored source is not hypothetical: it produced a false failure
   on `main` immediately after #736 merged, and the disassembly showed the
   mutation still resident in cached bytecode while the source was correct.

## Order and dependency

PR 1 must merge before PR 2 pushes. PR 2 rebased on `main` after PR 1 lands, not
merged into it — the cap value has to be the one already on `main` when CI
measures PR 2, or PR 2's cap check is passing against a ceiling that does not
exist yet.

## What closes the criteria

| Criterion | Closed by |
|---|---|
| 1 — `[::1` and `[::1]evil.com` refused, `[::1]:8767` served | PR 2, table test |
| 2 — mutation-tested, not covered | PR 2, verification step 3 |
| 3 — unparsed header returned, never `""` | PR 2, the `else ""` mutation |
| 4 — unbracketed path examined and stated | `design.md` open question 4; the branch comment in PR 2 |
| 5 — cap re-derived in its own change, ahead of the fix | PR 1 |
