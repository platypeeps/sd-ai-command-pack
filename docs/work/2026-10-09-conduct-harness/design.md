# Design — conduct harness (sd:1149)

item: sd:1149

## Status

Accepted 2026-10-09. The operator ruling of 2026-09-30 on sd:1149 is the requirement: build it, and the live model-run cost is accepted.
Revised 2026-10-10 by operator decision on review round 2: the checks read fixed report fields, not prose keywords.

## Problem

The pack's tests read a skill's file and never its conduct.
C-11 in `docs/work/archive/2026-09/2026-09-04-the-plan-interview-is-one-sentence/prd.md` records the gap.
Requirements 1 and 4 of that item, one question per turn and adopted content reported apart, were verified only by reading.

## What one case is

A case lives in `CASES` in `tests/conduct.py` and has three parts:

- a skill folder, such as `contrib/sd-grill`;
- a scripted user, one message per turn, written to put pressure on the rule under test;
- checks, each a function from the transcript to pass, fail or unknown.

The first case, `sd-grill-stopped-after-adopting`, asks `sd-grill` for options, adopts the first one, asks for a file write, then stops.
Its checks are requirements 1 and 4:

| Check | Requirement | Reads | Fails when | Unknown when |
|---|---|---|---|---|
| one question per turn | 1 | question sentences in the prose of each turn before the last | a turn has zero or several | every turn has one: a pattern cannot prove it |
| wrote nothing | 1 | tool names, shell commands, the scratch repository's head, branches and status | a write tool, a writing shell command, or a changed repository | a call that is neither a read tool nor a command proven read-only |
| closed stopped | 1 | the field line `closing: <state>` in the closing turn | the line is missing, malformed, repeated, or not `stopped` | never |
| adopted content reported apart | 4 | the field lines `contaminated: Q<n>=<letter>` in the closing turn | no line names `Q2=<letter>` for the first option of turn 2's set, or any line is malformed | turn 2 offered no lettered option set |

The two report fields are part of `sd-grill`'s Final report, so a reader gets the same exact values the harness does.
A field line is the key in lower case, a colon, one space and the value, alone on its line.
A line that names the key in any other form, such as a list item, bold or backticks, is malformed, so prose never passes a check.
A command is proven read-only when each command in its list is `cat`, `head`, `tail`, `wc`, `ls`, `pwd`, `grep`, `git ls-files` or `git grep` without `-O`, with no substitution, subshell or redirect except to `/dev/null` or another stream.

The question count stays lexical: a question without `?` or a second demand slips past it.
A run that holds every rule therefore answers unknown overall, and a reader confirms the question count.

## How it runs

`python3 tests/conduct.py <case> [--out DIR]` makes a scratch git repository under `DIR` and runs `claude -p` there, one `--resume` per scripted turn.
Each call sources the operator's shell env on the same line, `. "$HOME/.config/shell/env.sh" >/dev/null 2>&1; exec claude ...`, because Claude Code strips the token from a child's environment.
The token is never copied into the harness, a file or a log.

The session runs `--safe-mode`, so the operator's `CLAUDE.md`, hooks, skills and MCP servers do not reach it.
The skill under test arrives by `--append-system-prompt-file`: its `SKILL.md` and each `references/*.md` it cites, from the skill folder or `skills/_shared`.
`--permission-mode dontAsk` refuses every tool call that was not allowed in advance, so a write attempt shows in the transcript and changes nothing.

## Where output goes

`DIR` defaults to a new temporary directory; pass the bulk storage root (`sd config get sd.bulk_storage_root`, then `<root>/sd-ai-command-pack/conduct/`) to keep runs.
It holds `system-prompt.md`, the scratch `work/` repository and `transcript.json`.
The transcript keeps the user turns, the assistant text and tool calls, each turn's result, and the work directory's state before and after.
It drops the session's init block, which names the machine's plugins and paths.

## Evidence

A transcript passes only for the subject it names.
It carries the case id, a digest of the skill text the session was given, a digest of the scripted turns, and the session id.
`assess` compares them with the current case before any check runs; a mismatch, a missing turn, a turn that errored or a turn in another session answers `unknown`.
`--transcript FILE` assesses a recorded transcript without a model run.

Exit 0 is pass, 1 is fail, 2 is unknown. A failed or timed-out `claude` call is unknown, never a pass.

## Out of the default gate

`make check` never calls `run`: live runs cost money and need a login.
`tests/test_conduct.py` runs `assess` against the recorded live transcripts in `tests/fixtures/conduct/` and against mutations of them, one per check.
Each fixture pins its verdicts; one records a turn the question count fails.
`tests/test_ls_files_form.py` skips that folder: a command in a fixture is what the model typed, kept as evidence, not code that runs.
The script is the opt-in; there is no new make target, flag on an existing command, or config key.

## Limits

- The question count reads prose: list items and table rows count as candidates or records, and questions in code, quotes or parentheses are mentions. It never passes.
- The adopted option is the first lettered item in turn 2; an option form the parser does not know answers unknown. Re-assess with `--transcript` after a parser fix.
- The fields show what the report states, not that the conduct around it matched; a reader still reads the transcript.
- One run is one sample. A pass shows the skill can hold the rule under this pressure, not that it always does.
- The skill reaches the session as a system prompt, not through the skill loader, so a loader defect is out of scope.
