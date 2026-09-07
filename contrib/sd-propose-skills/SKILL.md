---
name: sd-propose-skills
description: Use when the user wants the current session reviewed for recurring friction, repeated steps, and hard-won gotchas, and high-bar skill proposals drafted into the report for the user to decide.
---

# sd-propose-skills

Turn what the current session actually taught into reviewable skill proposals, so
a lesson learned the hard way is not lost when the session ends. Do the judgement
and the drafting; the user decides each proposal by reading the report. Nothing is
filed automatically, and **nothing is written to a vault at all** -- item A's
criterion 28 removed that, because a proposal in somebody's vault is a record
with no reader and no expiry. What survives review becomes a row instead:
`sd suggest add "<the proposal>" --item <work item>` writes one, and
`sd suggest publish --to owner/repo --note <id>` files it where it can be
argued with.

A proposal is expensive to read and cheap to skip, so the bar is high on purpose:
most sessions should yield zero or one, not a list.

## When to use

Use at the end of a working session, or when the user asks to capture what a
session taught as reusable skills — phrasings like "review this session for
skills", "propose skills from what we learned", or "what should we build from
this". Use it only for the session in context; it does not read past sessions or
external transcripts.

Do not use it to improve an existing skill (that is editing, not proposing), or
to file tasks. It writes no file anywhere; the report is the whole output.

## Arguments

Argument names and value sets follow the shared vocabulary in `references/argument-vocabulary.md`; reuse a canonical name and its value set before coining a new one.

Arguments arrive as free text. Unknown argument names are an error — stop and
identify them before reviewing the session or writing anything.

- `target=` — retired. It named a vault this skill no longer writes to. Passing
  it is an error rather than a no-op, so a caller learns the output moved
  instead of watching for a file that never appears.
- `profile=` — retired with `target=`, and an error for the same reason. It
  resolved a destination, and there is no longer one to resolve.
- `context=` — the workspace or project label named in the report. Defaults to
  the current project or repository name; the user may adjust it.

There is no destination to resolve. The skill drafts its proposals into its
report, always, and the report is where the user reads them.

## Workflow

1. Review the current session for candidate skills — a step repeated across
   turns, the same friction hit more than once, a defect class that recurred, a
   workaround discovered mid-task, a precondition or ordering that bit and had to
   be re-derived.
2. Hold every candidate to the strict bar. A candidate qualifies only when all
   three hold: it recurred at least twice (or is a clearly recurring pattern); its
   repeatable core is mechanical (an enumeration, a check, a comparison, a fixed
   procedure) while the judgement is written once in the skill header; and there
   is a real cost of getting it wrong, where under-reporting fails silently. Drop
   everything else. Zero survivors is a valid, expected result — never invent a
   proposal to have something to show.
3. Give each survivor a kebab-case, filesystem-safe `<skill-name>`. Deduplicate
   first: skip, and report, any name that is already an installed skill or
   already sits in `contrib/`.
4. Render each survivor into the report using the sections below. There is no
   status field, because there is no note to carry one: the user's decision is
   made in the conversation the report is part of.
5. Report every survivor in full, what was skipped and why, and — when nothing
   cleared the bar — say so plainly. Zero is the common answer.
6. For a survivor the user accepts, write the row: `sd suggest add "<one line>"
   --item <work-item directory>`. That is what makes it outlive the session.

The report section per survivor:

```markdown
# <skill-name>

**What recurred.** <The specific thing, twice or more, with what it cost.>

**The mechanical core.** <The enumeration, check, comparison or fixed procedure
a skill would carry.>

**The judgement, written once.** <What the skill's header would settle so the
body does not have to re-decide it.>

**Cost of getting it wrong.** <Over-reporting: cheap and visible.
Under-reporting: invisible and the real failure. Name the silent-failure case.>
```

The `# <skill-name>` is the proposed skill's name, not this skill's.

## Safety rules

- **Write no file.** Not to a vault, not to `contrib/`, not to `docs/`. The
  report is the output, and `sd suggest add` is how the user makes one durable.
- Never advance a proposal's state and never file a task. The decision is the
  user's, made in the conversation.
- Never copy raw session output, secrets, credentials, or file contents into a
  proposal. Evidence describes the pattern.
- Prefer zero proposals over a weak one. Do not manufacture recurrence, evidence,
  or cost to clear the bar.
- If the session was shortened or summarized, work from the context that remains
  and do not fabricate instances that cannot be cited.

## Final report

- **Proposals** — each `<skill-name>` rendered in full, in the shape above;
- **Skipped candidates** — each with its reason (already installed, already in
  `contrib/`, or below the strict bar);
- **How to keep one** — the `sd suggest add` line for each proposal, ready to
  run; and
- **Nothing-to-propose** — an explicit statement when no candidate cleared the
  bar, rather than a padded list.
