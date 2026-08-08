# review-learnings asserts an absence no GitHub query ever tested

## Goal

Stop the generated learnings document from stating that no historical review
comments exist when no query was run to find out. The committed artifact should
never make a negative claim the tool did not test.

## Problem

`templates/scripts/sd-ai-command-pack-review-learnings.py:2262-2273`:

```python
lines.extend(["", "#### Historical Signal Clusters"])
shown_clusters = clusters[:MAX_HISTORICAL_CLUSTERS]
if clusters:
    ...
else:
    lines.append("- No historical Copilot review comments were included.")
```

`--github-days` defaults to `0` (`:2616`), so the documented bare `--update`
performs no GitHub query at all. The `else` branch then writes that line into
the document that gets committed.

Two different facts render identically:

- the query ran across N days and matched no clusters, and
- no query ran, so nothing could have matched.

The structured report already separates them — `--json` returns
`prsInspected: 0`, `cutoff: None`, `status: unavailable`. The information
exists. It just never reaches the artifact humans actually read.

## Problem, observed

`platypeeps/hoa-manager`. Running the documented `--update` without
`--github-days` rewrote the managed block of `docs/review-learnings.md`,
replacing populated historical clusters with the single line
`- No historical Copilot review comments were included.`

Nothing in the human-readable output indicated a skipped query rather than an
empty result. It was caught only by separately inspecting `--json`.

Re-running as `--update --github-days 45` restored the clusters and raised
every count:

```text
Task metadata        52 -> 71
Contract/doc drift   27 -> 45
Boundary validation  24 -> 38
Generated surfaces    8 -> 14
```

So the bare run had discarded real, still-current signal and replaced it with a
sentence asserting that signal did not exist.

## Why it matters beyond a wording nit

The output is a committed document that later readers — and later runs of this
same tool — treat as evidence. An untested negative is worse than a missing
section: a missing section prompts someone to go look, while
"No historical Copilot review comments were included." closes the question.

Had that write been committed without the cross-check, the repository would
have carried a confident negative claim that nothing had verified, in the one
document whose purpose is to accumulate review history.

## Requirements

### Functional

- The empty-clusters branch must state which case produced it: no query
  performed, versus a query that matched nothing.
- The no-query wording must name the remedy, so a reader can tell the tool was
  not asked rather than that the history is empty.
- The human-readable output must not contradict what `--json` reports for the
  same run.

### Non-functional

- No change to `render_target_update` splice behavior or the managed-block
  markers.
- Any default change must not silently increase API traffic for existing
  documented invocations without that being an explicit decision.

## Open questions

1. Should `--github-days` keep defaulting to `0`? Making the documented bare
   `--update` do the thing its own output implies changes what that command
   costs in API calls, which is a product call rather than a wording fix.
2. Should a bare `--update` that would overwrite populated clusters with an
   untested absence refuse outright, rather than warn? The observed run
   destroyed existing content; clearer wording alone would not have prevented
   that.

## Acceptance Criteria

- [ ] The no-query case and the empty-result case produce distinguishable text
- [ ] The no-query text names `--github-days` as the remedy
- [ ] A test asserts the human-readable line agrees with the `--json`
      `status` field for both cases
- [ ] Open questions 1 and 2 are answered in `design.md` with a decision

## Notes

Filed 2026-08-07. Reproducible on pack source `main` @ `4378d37b` (0.64.27) at
`:2273` / `:2616`. Not a stale-install artifact.

`scripts/sd-ai-command-pack-review-learnings.py` and its `templates/scripts/`
mirror are byte-identical today, so the line references above hold in both and
the fix must land in both.

Lower severity than a state-destroying defect — it degrades a generated
document and is recoverable by re-running with the right flag. Filed because it
is the same underlying shape as the preflight and work-loop defects logged the
same day: an absence reported without the check that would establish it.
