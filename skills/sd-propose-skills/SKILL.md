---
name: sd-propose-skills
description: Use when the user wants the current session reviewed for recurring friction, repeated steps, and hard-won gotchas, and high-bar skill proposals drafted into a configurable Obsidian Skill Proposals destination for later accept or decline.
---

# SE Propose Skills

Turn what the current session actually taught into reviewable skill proposals, so
a lesson learned the hard way is not lost when the session ends. Do the judgement
and the drafting; the user decides each proposal by flipping a dropdown in the
written note. Nothing is filed automatically, and nothing is written unless a
destination is resolved.

A proposal is expensive to read and cheap to skip, so the bar is high on purpose:
most sessions should yield zero or one, not a list.

## When to use

Use at the end of a working session, or when the user asks to capture what a
session taught as reusable skills — phrasings like "review this session for
skills", "propose skills from what we learned", or "what should we build from
this". Use it only for the session in context; it does not read past sessions or
external transcripts.

Do not use it to improve an existing skill (that is editing, not proposing), to
file tasks, or to write anything when no destination is configured — in that case
it reports inline instead.

## Arguments

Argument names and value sets follow the shared vocabulary in `references/argument-vocabulary.md`; reuse a canonical name and its value set before coining a new one.

Arguments arrive as free text. Unknown argument names are an error — stop and
identify them before reviewing the session or writing anything.

- `target=` — destination root. Notes are written under
  `<target>/System/Databases/Skill Proposals/`. An explicit `target` overrides
  profile resolution.
- `profile=auto|off|<locator>` — default `auto`. `auto` resolves only an
  attached, authorized, host-configured locator for the destination and never
  guesses a path; `off` forces inline-only and writes nothing; `<locator>` names
  a specific configured destination. Locator details stay private to the host and
  never appear in this skill.
- `context=` — the workspace or project label recorded in each note's `contexts`
  field. Defaults to the current project or repository name; the user may adjust
  it.

If neither an explicit `target` nor a resolvable locator is available, the skill
is destination-neutral: it drafts the proposals into its report and states how to
set a destination, rather than writing files.

## Workflow

1. Establish the write destination first, before drafting, so the run knows
   whether it will write or report inline. Resolve in order: `profile=off` means
   inline-only; an explicit `target=` wins next; `profile=auto` resolves an
   authorized host-configured locator; if nothing resolves, stay inline-only.
2. Review the current session for candidate skills — a step repeated across
   turns, the same friction hit more than once, a defect class that recurred, a
   workaround discovered mid-task, a precondition or ordering that bit and had to
   be re-derived.
3. Hold every candidate to the strict bar. A candidate qualifies only when all
   three hold: it recurred at least twice (or is a clearly recurring pattern); its
   repeatable core is mechanical (an enumeration, a check, a comparison, a fixed
   procedure) while the judgement is written once in the skill header; and there
   is a real cost of getting it wrong, where under-reporting fails silently. Drop
   everything else. Zero survivors is a valid, expected result — never invent a
   proposal to have something to show.
4. Give each survivor a kebab-case, filesystem-safe `<skill-name>`. Deduplicate
   before writing: skip, and report, any name that already exists as a note in
   the destination's `System/Databases/Skill Proposals/` folder (any status) or
   as an installed skill in the environment. Never overwrite an existing file.
5. Render each surviving proposal as a note using the exact template below. Copy
   the status-control line character for character — it is an inline-select
   control and only renders when verbatim. Write `status: proposed` and nothing
   else; the accept, decline, and filed states belong to the user and the
   destination's own filing routine.
6. Write one file per survivor to
   `<destination>/System/Databases/Skill Proposals/<skill-name>.md`, only when a
   destination resolved in step 1. Otherwise place the fully rendered notes in the
   report.
7. Report what was written, what was skipped and why, and — when nothing cleared
   the bar or no destination resolved — say so plainly.

The note template, reproduced exactly:

````markdown
---
contexts:
  - <context label>
area: Software Engineering
category:
  - Knowledge Management
content-type: skill-proposal
status: proposed
dateCreated: <YYYY-MM-DD today, unquoted>
description: <skill-name>
tags:
  - ai-generated
  - claude
  - sd-propose-skills
skill-name: <skill-name>
---

# <skill-name>

**Status:** `INPUT[inlineSelect(option(proposed), option(accepted), option(declined), option(filed)):status]`

**What it would do.** <The mechanical behavior in a few sentences: what it
enumerates, checks, compares, or produces, and the one hard rule that keeps it
honest.>

**Evidence.** <The concrete instances from this session — what recurred, how
often, what it cost. Describe the pattern, never paste raw command output,
secrets, tokens, or file contents.>

**Why a skill and not a note.** <The split: the mechanical part that repeats
versus the one-time judgement written in the header. Why a passive note would go
unread by the person who needs it at the moment it matters.>

**Cost of getting it wrong.** <Over-reporting: cheap and visible. Under-reporting:
invisible and the real failure. Name the silent-failure case.>

---

*This is a native note in this vault — the note itself is the record; there is no external ledger. Use the dropdown above rather than the frontmatter field — an off-vocabulary value is reported, not guessed at, so a typo reads as silence. Pick `accepted` to have `skill-proposal-accept` file it as a Trellis task in `sd-ai-command-pack`, or `declined` to close it. `filed` is set by the routine, not by you.*
````

The note's `# <skill-name>` and `skill-name:` are the proposed skill's name, not
this skill's. The `dateCreated` is an unquoted ISO date so the collection's
age formula parses it.

## Safety rules

- Write only when a destination resolved. With `profile=off`, or no `target` and
  no resolvable locator, write nothing and report inline.
- Only ever write `status: proposed`. The accept, decline, and filed states are
  the user's, set through the dropdown; this skill never advances them and never
  files a task.
- Never overwrite an existing note. A name collision is a skip, not a rewrite.
- The note is the record. Do not write an external ledger or add ledger fields.
- Never copy raw session output, secrets, credentials, or file contents into a
  note. Evidence describes the pattern.
- Never ship or embed a private destination path. The locator stays host-side.
- Prefer zero proposals over a weak one. Do not manufacture recurrence, evidence,
  or cost to clear the bar.
- If the session was shortened or summarized, work from the context that remains
  and do not fabricate instances that cannot be cited.

## Final report

- **Destination** — resolved target and how it resolved (`target`, locator, or
  inline-only), or the reason nothing resolved;
- **Proposals written** — each `<skill-name>` with its file path and a one-line
  summary;
- **Skipped candidates** — each with its reason (dedup against an existing note or
  installed skill, or below the strict bar);
- **Inline drafts** — the full rendered notes when no destination resolved, ready
  to paste once a target is set; and
- **Nothing-to-propose** — an explicit statement when no candidate cleared the
  bar, rather than a padded list.
