# add_session.py: support structured session content instead of auto-committing placeholders

## Summary

`add_session.py` writes journal entries containing hardcoded
placeholders — `(Add details)`, `(Add test results)`, `(see git log)` —
and then auto-commits them. Any team that gates journal quality (we
reject placeholder text in CI review checks) is forced into a
fill-and-amend dance after every session recording: run add_session,
manually patch the generated markdown, amend or re-commit. In one week
this happened six times for us and twice briefly landed placeholder or
wrong-hash content on main.

## What we built to work around it

A wrapper that composes the full entry before calling add_session, then
rewrites the generated sections and re-commits: resolves commit
subjects from git (fail-fast on unknown hashes), accepts repeatable
`--change` / `--test` / `--next-step` flags, verifies the final entry
is placeholder-free, and patches the journal variant-tolerantly because
different Trellis versions seed different section defaults. That last
part is the fragile bit: the wrapper anchors on generated headings and
default strings that Trellis may change at any time.

## Proposed upstream change (either would remove the workaround)

1. Accept structured content directly, e.g.
   `add_session.py --title T --summary S --commit h1,h2 --change "..."
   --test "..." --next-step "..."` (repeatable flags), rendering a
   complete entry with no placeholders; or
2. Keep the current interface but skip the auto-commit whenever the
   rendered entry still contains placeholder tokens, so callers can
   fill sections and commit once.

Option 1 is strictly better for automation; option 2 is a smaller
change that at least prevents placeholder commits.

## Environment

Observed against the Trellis CLI vendored scripts at `.trellis/.version`
0.6.5 (and several earlier versions; the placeholder behavior has been
stable across them).
