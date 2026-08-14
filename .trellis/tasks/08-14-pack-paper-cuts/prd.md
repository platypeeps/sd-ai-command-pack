# Pack paper cuts: write_json newline, set-meta floor, cache-env allowlist, PR-body closing keywords

Batch task for four small, independent fixes. The first three are relayed
from consumer evidence; the fourth was observed in this repository. Each is
under an hour; batching avoids four lifecycle rounds. If any one grows past
that, split it out rather than stretching this task.

## 1. Trellis write_json trailing newline (issue #413)

`.trellis/scripts/common/io.py` `write_json` omits the trailing newline that
`active_task.py:524` appends, so the same `task.json` has two byte
representations depending on the last writer, and hand-corrections revert
within a day (verified in this checkout: `io.py` dumps without `+ "\n"`).

Ownership caveat: `.trellis/scripts/` is Trellis-vendored tooling, not pack
payload — the pack cannot ship this fix to consumers, and a local edit would
be overwritten by the next Trellis update. The deliverable here is the
upstream handoff, prepared under the maintainer rule (`AGENTS.md`: no
upstream Trellis PR without explicit user approval for that specific PR):
write the paste-ready handoff for the one-character fix (append `"\n"` in
`write_json`, matching `active_task.py`; the `mkstemp`/`os.replace`
sequence, error handling, and return contract stay untouched), link it from
issue #413, and ask the user whether to open the upstream PR. Open it only
on that explicit approval; otherwise the handoff itself completes this item.
No bulk rewrite of existing files; no local vendored edit.

## 2. set-meta diagnostic states no Trellis version floor (issue #410)

`validateTrellisRootTaskBaseBranch`'s diagnostic recommends
`task.py set-meta` unconditionally; the command exists only from Trellis
v0.6.9. On 0.6.7/0.6.8 the recommended escape hatch is unreachable. Fix
(issue's shape 2, smallest): the diagnostic names the floor — "requires
Trellis >= v0.6.9; upgrade or set the base branch before deletion" — either
statically or by reading `.trellis/.version` when present.

## 3. cache-env consumers enforce membership again (issue #398)

Since A-080, `toolchain.sh` and `shell-lib.sh` export any all-caps pair the
cache-env emitter prints — shape-validated, membership-unchecked. Restore
membership enforcement without losing the single-authority property: the
consumers obtain the current key set from the library at runtime (a
`cache-env --keys` mode or a leading `KEYS=` line) and reject names outside
it. Adding a cache variable still requires no shell edit; unexpected names
fail loudly.

## 4. PR bodies may close issues the PR does not fix (issue #455)

`sd-create-pr`'s Safety Rules
(`templates/.agents/skills/sd-create-pr/SKILL.md:75-79`) constrain how a body
reaches `gh` — `--body-file`, never `--body`, because Markdown carries
backticks and command substitution — but say nothing about what the body may
contain. `gh pr merge` uses the PR title and body as the merge or squash
commit message unless `--subject`/`--body` override them, and the pack's
auto-merge does not override them
(`templates/scripts/sd-ai-command-pack-housekeeping.sh:762`, with
`$strategy_flag` set at `:741-755`). So a closing keyword anywhere in a
pack-authored body closes the referenced issue on the pack's own merge path.

Observed 2026-08-14 on PR #453, which filed a planning task to *own* issue
#401 and shipped no fix. Its body read "(P2, `planning`, closes #401)";
GitHub closed #401 as `COMPLETED` at the same second as the merge. Reopened
manually. Planning-artifact PRs are the exposed case, because naming the
issue a task owns is exactly their job.

Fix (the issue's item 1, smallest): add a Safety Rule stating that a closing
keyword followed by an issue reference is used only when the PR resolves that
issue, that a bare `#N` or `re: #N` mentions without closing, and why — the
body becomes the commit message. The issue's item 2, a preflight warning on a
closing keyword for an unowned issue, is deliberately **not** taken here; it
is a new check with its own false-positive surface and does not fit this
task's size bar. Leave it recorded on the issue.

## Acceptance Criteria

- [ ] The `write_json` newline fix has a paste-ready upstream handoff linked
      from issue #413, and the upstream PR is opened only on explicit per-PR
      user approval per `AGENTS.md`; the regression test belongs to that
      upstream change, not to this repo.
- [ ] The base-branch exemption diagnostic states the v0.6.9 floor; a test
      asserts the message content.
- [ ] Both shell consumers reject a cache-env pair whose name is outside the
      emitted key set, proven by a test injecting a foreign name.
- [ ] `sd-create-pr`'s Safety Rules state the closing-keyword rule and the
      mechanism behind it, and the rule is present in the generated
      `.agents/`, `.claude/`, and plugin payload copies after `make sync` —
      verified by grepping the shipped surfaces, not just `templates/`.
- [ ] Item 1's upstream disposition is recorded on this task: either the
      per-PR user approval and the opened upstream PR, or an explicit
      handoff-only decision. This is the part of #413 that is not a code
      change here, and it is what makes item 1 finishable.

### On issue closure

Issue closure is deliberately **not** an acceptance criterion. #413, #410,
#398, and #455 were closed as `not planned` on 2026-08-14, when tracking for
this work moved to the Trellis task tree; the defects are unchanged and this
task still owns them. A criterion promising to close them would already be
satisfied and would prove nothing.

The shipping PR should still reference them for provenance — as bare `#413`,
`#410`, `#398`, `#455`, never with a closing keyword. Item 4 is the reason:
that PR does fix them, so the keyword would be defensible, but a reopened
issue would then be silently re-closed by prose. Reopen deliberately if the
issue tracker needs to show the work again.
