---
name: sd-effort-calibrate
description: Recommends a Claude effort level (low, medium, high, xhigh, max) for a task, subagent, skill, or recurring `claude -p` job. Resolves the level in effect today, proposes a starting level from task shape, and names where to set it. Optionally runs a small A/B eval of one frozen prompt at two or three adjacent levels, scores quality against a rubric fixed before the runs, and picks the lowest level that ties the best. Records one result line locally. Use when choosing or changing effort, after a model change, when a scheduled job runs slow or costly, or before adding `effort:` frontmatter or `--effort` to a job.
---

# sd-effort-calibrate

This skill recommends one effort level and the place to set it.
Resolving and recommending read local settings only and need no approval.
The optional eval runs `claude -p`, which spends money, so it has its own gate.

## Principles

Anthropic asks for measurement, not carried-over settings:

- "**Test your use case:** The impact of effort levels varies by task type. Evaluate performance on your specific use cases before deploying." (https://platform.claude.com/docs/en/build-with-claude/effort, best practices)
- "Run an effort sweep on your own evals rather than carrying settings over from an earlier model." (same page, Claude Opus 5.5)
- "Reserve `xhigh` and `max` for work where you've measured a quality gain." (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)
- "To get less thinking, lower the effort level first." (same page)

Level names do not compare across models.
Opus 5.5 at `medium` matches or exceeds Opus 5 at `high` on Anthropic's coding evals.
Effort covers all output: text, tool calls, and thinking.
Lower effort gives fewer and terser tool calls.
Effort is a behavioural signal, not a token budget.

## 1. Resolve the level in effect

Walk this chain for the target. The first hit wins.

1. `CLAUDE_CODE_EFFORT_LEVEL` in the environment. It beats frontmatter too.
2. `--effort <level>` at launch, or `/effort <level>` in the session.
3. `effort:` frontmatter of the active subagent or skill, for its scope only.
4. `modelSettings.<model-id>.effortLevel` in `settings.json`.
5. The model default: `medium` on Opus 5.5, `high` on most others.

Top-level `effortLevel` in `settings.json` does not apply to Opus 5.5 or later.
A `modelSettings` value equal to the default has no effect.
Settings reject `max`; only the env var or the flag carries it.
A `maxEffortLevel` setting or an org limit can cap the result.
Report the effective level and the source that set it.
Source: https://code.claude.com/docs/en/model-config.

## 2. Pick a starting level

| Level | Start here for |
|---|---|
| `low` | Mechanical or scoped work: triage, extraction, read-only subagents, short scheduled summaries |
| `medium` | Routine agentic work that balances speed, cost, and quality |
| `high` | Hard reasoning, multi-file coding, reviews and audits |
| `xhigh` | Long agentic or coding runs, over 30 minutes, with measured gain |
| `max` | Only with measured headroom; it tends to overthink |

Per model:

- Opus 5.5: start at `medium`. Test `low` for routine work.
- Fable 5.1: start at `high`. Step down once evals show quality holds.
- Sonnet 5: start at the default. Step down for latency-sensitive work.
- A model without `xhigh` falls back to the next level below.

Stop here when the task is one-off and cheap. Otherwise offer the eval.

## 3. Where to set it

| Scope | Syntax |
|---|---|
| One session | `/effort low`, or the slider in `/model` |
| One run | `claude --effort low`, also with `-p` |
| Subagent or skill | `effort: low` in its frontmatter |
| Per model, persistent | `"modelSettings": {"<model-id>": {"effortLevel": "low"}}` in `settings.json` |
| Every process in a shell | `CLAUDE_CODE_EFFORT_LEVEL=low` |
| Scheduled `claude -p` job | Pass the flag through the job's argument hook, for example `JOB_CLAUDE_ARGS="--effort low"` |

Prefer the narrowest scope that covers the target.
A global env var silently overrides every frontmatter value.

## 4. Optional A/B eval

Run the eval only after the user explicitly asks for it,
or approves the run count and the estimated cost.
State both before asking: runs per level times levels, and a cost estimate.
Loading this skill or invoking it does not approve the eval.

1. Freeze one prompt, one working directory, and one fixture state.
2. Pick two or three adjacent levels around the starting level.
3. Write the rubric before any run: three to five binary checks.
   Prefer scriptable checks, such as a `grep` or a test exit code.
   Otherwise use one blind judge at a fixed model and level.
4. Run each level two or three times, from the frozen directory:

   ```bash
   timeout 900 claude -p --effort low --output-format json "<prompt>" < /dev/null > run-low-1.json
   ```

5. From each JSON result, read `total_cost_usd`, `duration_ms`, `num_turns`, and `usage`.
6. Score each run against the rubric. Do not edit the rubric after a run.
7. Choose the lowest level whose median score equals the best.
   Report a tie as a tie. Report a spread wider than the gap as noise.

A scheduled job with side effects needs a dry-run fixture first.
Do not run the live job for calibration.

## 5. Record the result

Write one line per eval:
date, model, prompt id, levels, median cost, median time, scores, choice, setting changed.

Store it locally, never in this pack:

- a note on the work row: `sd task note <item> --kind decision --body "<line>"`, or
- a line in a log under the repository's `docs/dashboard/` folder.

Re-run the eval after each model change.

## Guardrails

- Cap the eval at nine runs in total.
- Close stdin on every `claude -p` call with `< /dev/null`, and bound it with `timeout`.
- Send no secrets, credentials, or sensitive prompts to an eval run.
- A test that runs a caller end to end switches off optional model stages, such as the `JEV_*` variables.
- Do not change top-level effort inside a cached conversation. It invalidates the prompt cache.
- Change one setting per eval. Report the old and the new value.

## State of the tooling

There is no `bin/` entrypoint. This skill is the implementation.
It lives in `contrib/` and does not install by default; `sd skill try sd-effort-calibrate` installs it.
Two points are not verified:

- Workflow `agent()` options document no `effort` key. Treat per-agent effort in a workflow as unknown.
- Whether `claude -p` reads `modelSettings` is untested. Pass `--effort` explicitly to a `-p` job, or run one `--output-format json` probe to settle it.
