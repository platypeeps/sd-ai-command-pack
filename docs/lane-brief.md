# Lane brief

A **lane** is one agent working one item in its own git worktree, reporting
back to the session that launched it. This page is the brief that agent
receives. Copy the template below into the launch prompt, fill every `<...>`,
and delete the clause that does not apply to the repository.

Keep the template here rather than rewriting it per session. Each numbered
rule in "How to work" was paid for by a session that got it wrong first; the
notes under [Why these rules](#why-these-rules) say which failure bought which
line, so nobody has to rediscover them.

Related pages: [`review-learnings.md`](review-learnings.md) for what reviews
have taught this repository, [`workflow-controls.md`](workflow-controls.md)
for the controls a run passes through.

## The template

> You are lane `<lane>` in the **<pack|system>** repository, `<checkout path>`.
> main is at `<sha>`.
>
> ### Set up your own worktree first
>
> The checkout is what the live daemons and the operator use. Do NOT switch its
> branch. Create your own worktree and work only inside it, with `/usr/bin/git`:
>
> ```
> /usr/bin/git -C <checkout path> fetch origin
> /usr/bin/git -C <checkout path> worktree add <scratchpad>/wt-<lane> -b fix/sd-<N>-<slug> origin/main
> ```
>
> Remove it when the lane ends, after the branch is pushed.
>
> ### Your item
>
> **sd:<N>** — `<title>`. Read it in full from the store; it is the authority,
> not this brief:
>
> ```
> sqlite3 -readonly ~/.local/share/sd/sd.db "SELECT id, status, priority, title, json_extract(body,'$.text') FROM item WHERE id=<N>;"
> sqlite3 -readonly ~/.local/share/sd/sd.db "SELECT id, kind, body FROM note WHERE item=<N> ORDER BY id;"
> ```
>
> `<one paragraph: the cited file:line, the quoted text, the related pull
> requests and decision notes to read>`
>
> **Scope.** Your files are `<paths>`. Other lanes hold `<paths>` in their own
> worktrees; do not touch those. If your work needs them, stop and tell me.
>
> `<owner-only questions next door, if any: name them and say they are NOT yours>`
>
> ### How to work
>
> 1. **Re-measure the premise before fixing anything.** Check every line number
>    and quoted string against your worktree. If the finding no longer holds,
>    say so with the measurement and do not manufacture work.
> 2. **Fail-first.** Watch the new test fail on the unfixed code, quote the
>    decisive assertion line, then fix, then watch it pass. A test that does not
>    kill its mutation has not earned its place.
> 3. **Mutations, with a byte-copy revert.** Before each mutation, copy every
>    file you will mutate: `cp <file> <scratchpad>/<lane>/pre/<file>`. Apply the
>    mutation, confirm the test dies naming itself, then restore from the copy
>    and prove it: `diff -q <scratchpad>/<lane>/pre/<file> <file>` must return
>    rc 0. Never prove a revert with `git diff --exit-code` or
>    `git checkout -- <file>`: when the mutated file is one your change modifies
>    and the fix is uncommitted, rc 0 against HEAD means the fix was LOST, not
>    preserved. Record the exact failure text of each mutation.
> 4. **Gate.** `<gate command>`. Never end a gate command with a pipe; the
>    reported status is the pipe's. Redirect to a file and grep it afterwards.
>    Report rc, suite count, test count, and a grep for `FAILED`/`ERROR`.
>    `<extra checks: shellcheck, ruff, mypy>`. Run the suites with the
>    environment CI uses; do not point `HOME` at a scratch directory, because
>    the suites resolve the store and the config from the real one and the
>    worktree cannot execute that clause.
> 5. **Time.** Never state an elapsed duration unless the current time and the
>    start time come out of the SAME command: `date -u` beside the API
>    timestamp, in one call. A check run can report `status: in_progress` while
>    carrying a `completed_at` in the past; trust the timestamps, not the status
>    field.
> 6. **Review cap is 1, plus one verification of the fix.** Read the review
>    through `mcp__github__pull_request_read` `get_reviews`, never through
>    thread counts: the verdict line, `Comments generated: N`, the
>    `Suppressed comments (N)` section, the per-file table, `Files reviewed:
>    N/M`, and the effort level. A suppressed finding has no thread and
>    `get_review_comments` does not show it. `copilot-pull-request-reviewer` may
>    run more than once on one pull request, may not re-run on a push, and may
>    fail outright with a body that is an error message rather than a verdict —
>    so key every review by its `commit_id`, read every one the call returns,
>    and check again after each push. Quote every finding verbatim and address
>    or rebut each with evidence.
>    `<system only: do NOT request a Copilot review; that repository's CLAUDE.md
>    forbids it, because its CI runs the reviewer itself.>`
>
> ### Rules
>
> - Do NOT use `gh`. Use the `mcp__github__*` tools. Load their schemas with one
>   `ToolSearch` call.
> - Do NOT write to the live store, `~/.local/share/sd/sd.db`. Read it with
>   `sqlite3 -readonly`. Do not run any `sd` write verb. I close the item.
> - Do NOT restart the dashboard or the runner, and do not run `launchctl`.
>   I deploy.
> - Never write into the pack `.venv`. Never base a venv on another lane's copy.
> - Before editing a file, check it against every open pull request in the
>   repository (`list_pull_requests`, then `pull_request_read get_files`). If a
>   file you need is in an open pull request, tell me and WAIT. Do not merge
>   main into your branch; check
>   `/usr/bin/git merge-tree --write-tree origin/main HEAD` rc 0 before the push
>   instead.
> - Namespace every scratchpad file under `<scratchpad>/<lane>/`.
> - If a command is refused by the permission classifier, do not retry it by
>   evasion and do not split it to get around the refusal. Re-run it in a
>   simpler form or report the refusal.
> - Kill only your own processes, by pid.
>
> ### The pull request
>
> - Title: `fix(sd:<N>): <what is now true>`.
> - First line of the body: `Work: sd:<N>`. Then the problem, the fix, the tests
>   with fail-first lines, the mutation table, the gate lines, and a
>   **NOT VERIFIED** section.
> - Run `bin/sd-docs-lint --pr-body <body file>` from the pack checkout with its
>   `.venv/bin/python`. It must end `sd-docs-lint: clean`. Note that it passes a
>   body lacking the template's scope section, so check that section by eye.
> - End the body and the commit message with the attribution lines the session
>   is using.
> - One push, then freeze the head until the review is read. Do NOT merge.
>   I merge.
>
> ### Report back
>
> Write the full report to `<scratchpad>/<lane>/tail.md` (`mkdir -p` first); the
> message channel truncates. Then send one line to the launching session:
> `<lane>: PR #<n> at <sha>, CI <state>, report at <path>`, or
> `<lane>: BLOCKED <why>`.
>
> The report holds: whether the citation held, the fail-first line, the mutation
> table with exact failure text and each `diff -q` rc, the gate numbers, the
> pull request number and head sha, every CI leg with its conclusion and
> `completed_at`, the reviewer's verdict line and suppressed count, every
> finding quoted verbatim with your disposition, a **NOT VERIFIED** section, and
> a proposed decision note in plain text with no backticks. If the item turns
> out to be already fixed, or wrong, close it out with the measurement instead
> of inventing a change.

## Why these rules

**Rule 3, the byte-copy revert.** A lane proved a mutation reverted with
`git diff --exit-code` while its own fix was still uncommitted. The command
compares against HEAD, so rc 0 meant the fix had been thrown away along with
the mutation — the strongest possible evidence that the revert worked, reported
by a check that cannot tell the two apart. A pre-mutation byte copy and
`diff -q` compare against the intended state instead.

**Rule 4, the real HOME.** Pointing `HOME` at a scratch directory looks like
good hygiene and breaks the suites, which resolve the store and the
configuration from the real one.

**Rule 5, one command for both timestamps.** Durations computed from a
remembered start time have been wrong by hours. A check run can also report
`status: in_progress` while already carrying a past `completed_at`; the
timestamps are the fact, the status field is not.

**Rule 6, read the whole review body.** Counting threads misses every
suppressed finding, because a suppressed comment has no thread at all — it
exists only in the `Suppressed comments (N)` section of the review body.

**Rule 6, key reviews by commit.** The reviewer was long believed to run once
per pull request, on the first head only. That is false: it ran on two heads of
one pull request more than once, it has also declined to re-run on a plain
push, and it has returned a body that is only an error message rather than a
verdict. What decides which happens is not known, so a lane must read every
review the API returns and check again after each push rather than assume.
