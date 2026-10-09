# Design — conduct harness (sd:1149)

item: sd:1149

## Status

Accepted 2026-10-09. The operator ruling of 2026-09-30 on sd:1149 is the requirement: build it, and the live model-run cost is accepted.

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

| Check | Requirement | Fails when |
|---|---|---|
| one question per turn | 1 | a turn before the last asks zero or several questions; a list item is a candidate, not a question |
| wrote nothing | 1 | a write tool or a writing shell command is called, or the scratch repository's head, branches or status change |
| closed stopped | 1 | the closing state says `completed`, or does not name `stopped` |
| adopted content reported apart | 4 | the closing report has no assistant-supplied section, the section says none, or it does not mark the answer contaminated |

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
A fixture is kept when its report shape once fooled the parser; each must pass.
`tests/test_ls_files_form.py` skips that folder: a command in a fixture is what the model typed, kept as evidence, not code that runs.
The script is the opt-in; there is no new make target, flag on an existing command, or config key.

## Limits

- The checks read the model's prose. A question count is a heuristic: list items and table rows count as candidates or records, and questions in code, quotes or parentheses are mentions.
- A report shape the parser does not know reads as a fail, as the first two live runs did. Re-assess with `--transcript` after a parser fix, and keep the transcript as a fixture.
- One run is one sample. A pass shows the skill can hold the rule under this pressure, not that it always does.
- The skill reaches the session as a system prompt, not through the skill loader, so a loader defect is out of scope.
