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
> /usr/bin/git -C <checkout path> worktree add <scratchpad>/wt-<lane> -b fix/sd-<N>-<slug> <sha>
> ```
>
> Start from `<sha>`, the base named at the top of this brief — not from
> `origin/main`. They are the same only until main moves, and main moving is
> what the sha is there to pin. Branch from `origin/main` and a lane launched
> minutes ago silently carries somebody else's commits, which then appear in
> its diff and its review. If `<sha>` is not in the checkout after the fetch,
> stop and say so rather than substituting a branch name.
>
> Remove the worktree when the lane ends, after the branch is pushed.
>
> ### Your item
>
> **sd:<N>** — `<title>`. Read it in full from the store; it is the authority,
> not this brief:
>
> ```
> <pack checkout>/bin/sd store item <N> --json
> ```
>
> That is the canonical read — the row, every note, and the revision, in one
> call. It is a read verb; it writes nothing. Do not hand-roll a `sqlite3`
> projection instead: one written from the schema you remember drops the fields
> you were not thinking about, and `repo` is the one that matters most.
>
> Invoke it by checkout-relative path, `bin/sd`, never as a bare `sd`. That is
> the only calling convention this repository supports
> ([`AGENTS.md`](../AGENTS.md), "Calling Convention"), and a bare name resolves
> against whatever `PATH` happens to hold. The store is machine-wide, so a
> `system` lane uses the pack checkout's `bin/sd` to read its own item; the
> rows are the same rows.
>
> **Check `repo` before you touch anything.** It names the checkout the row
> belongs to. If it is not the checkout you were given, stop and print both
> paths, exactly as [`skills/sd-plan/SKILL.md`](../skills/sd-plan/SKILL.md)
> requires. Work done in the checkout the agent picked is the failure that rule
> exists to prevent.
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
>    file you will mutate. The paths are nested, so make the parent first or
>    `cp` aborts before the mutation even runs:
>
>    ```
>    dest=<scratchpad>/<lane>/pre/<file>
>    mkdir -p "$(dirname "$dest")" && cp <file> "$dest"
>    ```
>
>    Apply the mutation, confirm the test dies naming itself, then restore from
>    the copy and prove it: `diff -q <scratchpad>/<lane>/pre/<file> <file>` must
>    return rc 0. Never prove a revert with `git diff --exit-code` or
>    `git checkout -- <file>`. Both answer a question about the index, not about
>    your bytes: bare `git diff` compares the worktree with the index, and
>    `checkout --` restores the file from the index. So when the mutated file is
>    one your change also modifies and that fix is unstaged, `checkout --`
>    discards the fix along with the mutation and `git diff --exit-code` then
>    reports clean — success, from the one check that should have caught it.
>    Stage the fix and the same commands behave differently again. The answer
>    depends on the index's state, which is not what you are measuring. A byte
>    copy compares against the bytes you intended, whatever the index holds.
>    Record the exact failure text of each mutation.
> 4. **Gate.** `<gate command>`. Never end a gate command with a pipe; the
>    reported status is the pipe's. Redirect to a file and grep it afterwards.
>    Report rc, suite count, test count, and a grep for `FAILED`/`ERROR`.
>    `<extra checks: shellcheck, ruff, mypy>`. Run the suites with the
>    environment CI uses; do not point `HOME` at a scratch directory, because
>    the suites resolve the store and the config from the real one and the
>    worktree cannot execute that clause.
> 5. **Time.** Never state an elapsed duration from a start time you
>    remembered. Both ends must come from one source, and there are only two
>    that qualify. For anything timed against an API, subtract two timestamps
>    carried by the SAME response — `started_at` and `completed_at` of one check
>    run, say. For anything timed locally, emit both ends from one shell
>    command. `date -u` in the terminal beside a timestamp from an MCP call does
>    NOT qualify: they are two calls, taken at two moments, and the gap between
>    them is exactly the quantity you are claiming to measure. If neither source
>    gives you both ends, state the two timestamps and omit the duration. A
>    check run can also report `status: in_progress` while carrying a
>    `completed_at` in the past; trust the timestamps, not the status field.
> 6. **Review cap is 1, plus one verification of the fix.** Read the review
>    through `mcp__github__pull_request_read` `get_reviews`, never through
>    thread counts: the verdict line, `Comments generated: N`, the
>    `Suppressed comments (N)` section, the per-file table, `Files reviewed:
>    N/M`, and the effort level. A suppressed finding has no thread and
>    `get_review_comments` does not show it. `copilot-pull-request-reviewer` may
>    run more than once on one pull request, may not re-run on a push, and may
>    fail outright with a body that is an error message rather than a verdict —
>    so key every review by its `commit_id`, read every one the call returns,
>    and check again after each push. A review whose `commit_id` is not your
>    current head says nothing about your current head: it is evidence about the
>    code it ran on, and nothing else. An error body is not a verdict either.
>    The round is answered only by a review that names the head you pushed AND
>    carries a real verdict; anything else means keep waiting, not proceed.
>    Quote every finding verbatim and address or rebut each with evidence.
>    `<system only: do NOT request a Copilot review; that repository's CLAUDE.md
>    forbids it, because its CI runs the reviewer itself.>`
>
> ### Rules
>
> - Do NOT use `gh`. Use the `mcp__github__*` tools. Load their schemas with one
>   `ToolSearch` call.
> - Do NOT write to the live store, `~/.local/share/sd/sd.db`, and do not run
>   any `sd` write verb. I close the item. Read it with `bin/sd store …`, as
>   above. `sqlite3 -readonly` is for the questions that command cannot answer —
>   counting rows, joining tables — and never as a substitute for the canonical
>   item read.
> - Do NOT restart the dashboard or the runner, and do not run `launchctl`.
>   I deploy.
> - Never write into the pack `.venv`. Never base a venv on another lane's copy.
> - Before editing a file, check it against every OTHER lane's open pull
>   request (`list_pull_requests`, then `pull_request_read get_files`; skip your
>   own number once you have one). If a file you need is in another lane's open
>   pull request, tell me and WAIT. Your own pull request holds every file you
>   are fixing, so a check that does not exclude it stops the review-fix pass
>   on itself. Do not merge
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
> - Pack lanes only: run `sd-docs-lint` with your own worktree as the working
>   directory, invoking the pack interpreter explicitly. It resolves the
>   repository from cwd, not from where the script lives (`bin/sd-docs-lint`,
>   the `R10-D6` comment), so running it from the pack checkout lints the pack
>   and tells you nothing about your branch:
>
>   ```
>   cd <your worktree>
>   <pack venv python> bin/sd-docs-lint --pr-body <body file>
>   ```
>
>   Run your own `bin/sd-docs-lint`, the one in the worktree — not the copy in
>   the pack checkout. If your branch changes the linter, the pack's copy does
>   not exercise that change and the result is about code you did not write.
>   Name the interpreter by the path I give you rather than hard-coding one;
>   a checkout lives wherever it lives.
>
>   It must exit 0 and end `sd-docs-lint: clean`. Note that it passes a body
>   lacking the template's scope section, so check that section by eye. A
>   `system` lane does not run this at all; the linter is a pack tool.
> - End the body and the commit message with the attribution lines the session
>   is using.
> - One push, then freeze the head until the review has been read and
>   dispositioned. You get one further push after that: every review fix in a
>   single batch, gate re-run before it, never one commit per finding. That
>   second push is what the verification round reviews. A third push needs me
>   to say so. Do NOT merge — I merge.
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
> out to be already fixed, or wrong, report that measurement and stop. Do not
> close it yourself — the rule above stands, I run every `sd` write verb and I
> close the item.

## Why these rules

**Rule 3, the byte-copy revert.** A lane proved a mutation reverted with
`git diff --exit-code` while its own fix sat unstaged in the same file. Bare
`git diff` compares the worktree with the index, so once the revert had taken
the fix away with the mutation, the two matched and rc 0 said clean — the
strongest possible evidence that the revert worked, produced by a check that
cannot tell a restored file from a lost one. Stage the fix instead and the same
commands answer differently, which is the point: they report on the index, and
the index is not what you are measuring. A byte copy compares against the bytes
you meant to have.

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
