# Research repo conventions

Applies to this repo. Full standard: run `sd-research-kit conventions` for its path,
or read it in the pack at `skills/sd-research-repo/references/conventions.md`.

## Layout

| Path | Holds |
|---|---|
| `00-overview/` | `understanding.md`, `open-questions.md`, `next-research.md` — fixed names |
| `10-sources/` | `registry.md` (what was read, when, status), `references.md` (link list) |
| `20-map/` | `MAP-*.md` — structured ledgers, crosswalks, comparisons |
| `30-brief/` | `BRIEF-*` argued positions · `REVIEW-*` assessments · `SUMMARY-*` condensations |
| `40-docs/` | `PRD-` `DESIGN-` `PLAN-` `SPIKE-` `DISCOVERY-` `BENCHMARK-` `DECK-` `OUTREACH-` |
| `90-scratch/` | Throwaway and superseded. Never cited. |
| `build/` | Rendered HTML. Generated — never hand-edit. Gitignored. |
| `vendor/` | Third-party clones. Gitignored. |

Use only the directories this repo needs; do not invent new ones.

## Documents

Every document opens with an H1, a provenance paragraph, then `---`:

```markdown
# Title

Compiled 2026-08-27 from `owner/repo` @ `abc1234`, plus <other sources>.

---

## 1. First section
```

The renderer strips everything above `---` and builds the masthead from
`research.conf.py`, so that block is for readers of the markdown.

- `##` headings become the rail nav. Number them when order matters.
- State what is **verified** and what is **not verified** in a closing Status section.
- Corrections stay visible — say what changed and why, do not silently overwrite.

## Rendering

```bash
sd-research-kit render
```

Writes `build/<name>.html` — standalone, opens with `file://`. That is a local
reading form, not a publishing surface. (`build/artifact/<name>.html` is still
emitted, but nothing consumes it: research is not published as artifacts.) Add or
edit pages in `research.conf.py`, never by editing generated files.

## Adversarial review before publishing

Nothing is published until it has been reviewed against itself — the **information** it
rests on, and the **product** the reader receives. The mechanical half:

```bash
sd-research-kit review
```

It checks provenance blocks, Status sections and build freshness, then prints the checklist
for the half no script can do. Exit 1 means fix it first.

The information — take it adversarially, the job is to refute:

1. List the load-bearing claims: removing one changes the conclusion.
2. Open each cited source again and read it. Default to refuted — the source must *say* it,
   not merely be consistent with it.
3. Numbers: check the unit, the date and the denominator, not the digits.
4. An unsupported claim is cut, or moved to Status as explicitly unverified. It never stays
   in the body, where a reader assumes it was checked.
5. Say what you could not check and why.

The product — read what the reader gets, not what you meant:

6. Read the rendered page cold. Does the conclusion follow from what is on the page?
7. Find the load-bearing assumption the document never states.
8. After mirroring, check Notion against the source, and that handling restrictions survived
   the mirror.

The second reader is Codex. Where the `codex@openai-codex` plugin ("Codex for Claude") is
installed, the independent pass runs through it instead of being skipped:

```
/codex:setup                              # once per machine: ready, CLI present, logged in
/codex:adversarial-review --scope working-tree \
  "This is a markdown research brief, not code. Attack the argument, not the syntax: which
   load-bearing claims does the cited source not actually support; which numbers are missing
   a unit, a date or a denominator; what does the conclusion depend on that the document
   never states?"
```

It reviews a **git diff**, so the document has to be in the working tree or the branch diff
(`--base main`) — already committed on `main`, it is invisible to the command. Its default
framing is a code review, hence the focus text. Anything past a page runs in background:
`/codex:status`, then `/codex:result`. It sees the repo, not the sources, so step 2 —
reopening the citation — stays yours.

Record the outcome in the Status section: what was verified and how, what was not, what was
cut, and the Codex pass — date, what it raised, what changed, what was rejected and why. A
review that found nothing says what it checked. If the plugin or CLI is unavailable
(`/codex:setup` reports it), say that in Status: "no independent pass" is a stated gap.

## Publishing — Notion, not artifacts

**Do not publish research as a Claude artifact.** Notion is the publishing surface.

Every overview, map, brief, report, and survey in this repo has a Notion page under
the repo's folder in https://app.notion.com/p/3c9f52b1578281a7a466fb0e2df4d928, kept in sync when the source
document changes. The markdown file is the source of truth; Notion is the readable,
shareable mirror. `90-scratch/` is not mirrored.

Mirror shape — full content minus the H1, opening with a pointer back to the file:

```markdown
*Source: **`/Users/sven/repos/...`** — edit there, then update this page.*

<the document's provenance line>

---

## 1. First section
```

Give each page an icon and keep it stable across updates — a changed icon reads as a
different page. Record every page in the README's **Notion pages** table: document,
page title, URL.

## Style

- Absolute paths when pointing at a local file: `file:///Users/...`, not a bare path.
- Prefer a number with its validation status over an adjective.
- One claim, one source. If it came from Jira, cite the ticket; from code, cite `file:line`.
